# logic for /artifacts

from searcch_backend.api.app import db
from searcch_backend.models.model import *
from searcch_backend.models.schema import *
from flask import abort, jsonify, url_for, request
from flask_restful import reqparse, Resource
from sqlalchemy import func, desc, sql, or_, and_, exc
from searcch_backend.api.common.auth import (verify_api_key, has_api_key, has_token, verify_token)
import math
import logging
import json
from sqlalchemy.dialects import postgresql

LOG = logging.getLogger(__name__)

def generate_artifact_uri(artifact_group_id, artifact_id=None):
    return url_for('api.artifact', artifact_group_id=artifact_group_id,
                   artifact_id=artifact_id)

# Method written with the help of ChatGPT
def sort_artifacts_by_criteria(artifacts, keywords=None):
    def custom_sort(artifact):
        if keywords:
            # Count the number of keyword matches in the title field
            keyword_count = sum(1 for keyword in keywords if keyword in artifact['title'])
        else:
            keyword_count = 0
        
        # Sort by descending order of the last 8 characters
        sorting_key = (keyword_count, artifact['title'][-8:], artifact['title'])          
        return sorting_key
    
    # Sort the artifacts using the custom sorting function
    sorted_artifacts = sorted(artifacts, key=custom_sort, reverse=True)
    
    return sorted_artifacts

# Method written with the help of ChatGPT
def paginate(sorted_artifacts, page_num, items_per_page):
    start_index = (page_num - 1) * items_per_page
    end_index = start_index + items_per_page
    return sorted_artifacts[start_index:end_index]


def search_artifacts(keywords, artifact_types, author_keywords, organization, owner_keywords, badge_id_list, page_num, items_per_page, category, groupByCategory):
    """ search for artifacts based on keywords, with optional filters by owner and affiliation """
    sqratings = db.session.query(
        ArtifactRatings.artifact_group_id,
        func.count(ArtifactRatings.id).label('num_ratings'),
        func.avg(ArtifactRatings.rating).label('avg_rating')
    ).group_by("artifact_group_id").subquery()
    sqreviews = db.session.query(
        ArtifactReviews.artifact_group_id,
        func.count(ArtifactReviews.id).label('num_reviews')
    ).group_by("artifact_group_id").subquery()

    # create base query object
    if not keywords:
        logging.disable(logging.INFO) # disable to prevent excessive logging of all artifacts when loading the search page for the first time
        query = db.session.query(Artifact,
                                    'num_ratings', 'avg_rating', 'num_reviews', "view_count", 'dua_url'
                                    ).order_by(
                                    db.case([
                                        (Artifact.type == 'pcap', 1),
                                        (Artifact.type == 'flowtools', 2),
                                        (Artifact.type == 'flowride', 3),
                                        (Artifact.type == 'fsdb', 4),
                                        (Artifact.type == 'csv', 5),
                                        (Artifact.type == 'custom', 6),
                                        (Artifact.type == 'netflow', 7),
                                        (Artifact.type == 'dataset', 8),
                                        (Artifact.type ==
                                         'publication', 9),
                                    ], else_=10)
                                ).order_by("category")
        query = query.join(ArtifactGroup, ArtifactGroup.id == Artifact.artifact_group_id
                        ).join(sqratings, ArtifactGroup.id == sqratings.c.artifact_group_id, isouter=True
                        ).join(ArtifactPublication, ArtifactPublication.id == ArtifactGroup.publication_id
                        ).join(sqreviews, ArtifactGroup.id == sqreviews.c.artifact_group_id, isouter=True
                        ).order_by((func.right(Artifact.title, 8)).desc())
    else:
        # search_query = db.session.query(ArtifactSearchMaterializedView.artifact_id, 
        #                                 func.ts_rank_cd(ArtifactSearchMaterializedView.doc_vector, func.websearch_to_tsquery("english", keywords)).label("rank")
        #                             ).filter(ArtifactSearchMaterializedView.doc_vector.op('@@')(func.websearch_to_tsquery("english", keywords))
        #                             ).subquery() 
        # Split the keywords into a list
        keyword_list = keywords.split()

        # Create a list of conditions for each keyword for partial matching on title
        title_conditions = [Artifact.title.ilike(f"%{keyword}%") for keyword in keyword_list]

        # Combine title conditions using OR operator
        combined_title_condition = or_(*title_conditions)
        query = db.session.query(Artifact, 
                                    'num_ratings', 'avg_rating', 'num_reviews', "view_count", 'dua_url'
                                    ).join(ArtifactPublication, ArtifactPublication.artifact_id == Artifact.id
                                    )
        
        query = query.join(sqratings, Artifact.artifact_group_id == sqratings.c.artifact_group_id, isouter=True
                        ).join(sqreviews, Artifact.artifact_group_id == sqreviews.c.artifact_group_id, isouter=True
                        ).filter(combined_title_condition)

    if author_keywords or organization or category:
        rank_list = []
        if author_keywords:
            if type(author_keywords) is list:
                author_keywords = ' or '.join(author_keywords)
            rank_list.append(
                func.ts_rank_cd(Person.person_tsv, func.websearch_to_tsquery("english", author_keywords)).label("arank"))
        if organization:
            if type(organization) is list:
                organization = ' or '.join(organization)
            rank_list.append(
                func.ts_rank_cd(Organization.org_tsv, func.websearch_to_tsquery("english", organization)).label("orank"))
        author_org_query = db.session.query(
            Artifact.id, Artifact.provider, *rank_list
        )#.join(ArtifactAffiliation, ArtifactAffiliation.artifact_id == Artifact.id
        # ).join(Affiliation, Affiliation.id == ArtifactAffiliation.affiliation_id
        # )
        if author_keywords:
            author_org_query = author_org_query.join(Person, Person.id == Affiliation.person_id)
        if organization:
            author_org_query = author_org_query.filter(organization == Artifact.provider)
        if category:
            if type(category) is list:
                author_org_query = author_org_query.filter(Artifact.category.in_(category))
            else:
                author_org_query = author_org_query.filter(category == Artifact.category)
        if author_keywords:
            author_org_query = author_org_query.filter(
                Person.person_tsv.op('@@')(func.websearch_to_tsquery("english", author_keywords))).order_by(desc("arank"))
        if organization:
            author_org_query = author_org_query.filter(
                Organization.org_tsv.op('@@')(func.websearch_to_tsquery("english", organization))).order_by(desc("orank"))
        author_org_query = author_org_query.subquery()
        query = query.join(author_org_query, Artifact.id == author_org_query.c.id, isouter=False)

    if owner_keywords:
        if type(owner_keywords) is list:
            owner_keywords = ' or '.join(owner_keywords)
        owner_query = db.session.query(
            User.id, func.ts_rank_cd(Person.person_tsv, func.websearch_to_tsquery("english", owner_keywords)).label("rank")
        ).join(Person, User.person_id == Person.id
        ).filter(Person.person_tsv.op('@@')(func.websearch_to_tsquery("english", owner_keywords))).order_by(desc("rank")).subquery()
        query = query.join(owner_query, Artifact.owner_id == owner_query.c.id, isouter=False)
    if badge_id_list:
        badge_query = db.session.query(ArtifactBadge.artifact_id
            ).join(Badge, Badge.id == ArtifactBadge.badge_id
            ).filter(Badge.id.in_(badge_id_list)
            ).subquery()
        query = query.join(badge_query, Artifact.id == badge_query.c.artifact_id, isouter=False)

    #Add View number to query
    query = query.join(StatsArtifactViews, Artifact.artifact_group_id == StatsArtifactViews.artifact_group_id, isouter=True)
    
    # add filters based on provided parameters
    query = query.filter(ArtifactPublication.id != None)
    if artifact_types:
        if len(artifact_types) > 1:
            query = query.filter(or_(Artifact.type == a_type for a_type in artifact_types))
        else:
            query = query.filter(Artifact.type == artifact_types[0])


    dua_query = db.session.query(DUA).subquery()
    query = query.join(DUA, Artifact.collection == DUA.collection)

    query = query.distinct()
    if (groupByCategory):

        categoryDict = {}
        for row in query.all():
            artifact, num_ratings, avg_rating, num_reviews, view_count, dua_url = row
            if artifact.category not in categoryDict:
                categoryDict[artifact.category] = dict(count=0, artifacts=[])
            
            categoryDict[artifact.category]["count"]+=1
            categoryDict[artifact.category]["artifacts"].append(artifact.title)
           
        return dict(categoryDict=categoryDict)
    result = query.all()

    artifacts = []
    for row in result:
        artifact, num_ratings, avg_rating, num_reviews, view_count, dua_url = row

        abstract = {
            "id": artifact.id,
            "artifact_group_id": artifact.artifact_group_id,
            "artifact_group": {
                "id": artifact.artifact_group_id,
                "owner_id": artifact.artifact_group.owner_id
            },
            "uri": generate_artifact_uri(artifact.artifact_group_id, artifact_id=artifact.id),
            "doi": artifact.url,
            "type": artifact.type,
            "title": artifact.title,
            "description": artifact.description,
            "avg_rating": float(avg_rating) if avg_rating else None,
            "num_ratings": num_ratings if num_ratings else 0,
            "num_reviews": num_reviews if num_reviews else 0,
            "owner": { "id": artifact.owner.id },
            "views": view_count if view_count else 0,
            "dua_url": dua_url,
            "category": artifact.category,
            "shortdesc": artifact.shortdesc
        }

        artifacts.append(abstract)

    sorted_artifacts = []
    if keywords:
        sorted_artifacts = sort_artifacts_by_criteria(artifacts, keywords.split())
    else:
        sorted_artifacts = sort_artifacts_by_criteria(artifacts)

    artifact_page = paginate(sorted_artifacts, page_num, items_per_page)
    
    logging.basicConfig(level = logging.INFO)

    return dict(
        page=page_num,total=len(sorted_artifacts),
        pages=int(math.ceil(len(sorted_artifacts) / items_per_page)),
        artifacts=artifact_page)

class ArtifactSearchIndexAPI(Resource):
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument(name='keywords',
                                   type=str,
                                   required=False,
                                   help='missing keywords in query string')
        self.reqparse.add_argument(name='page',
                                   type=int,
                                   required=False,
                                   default=1,
                                   help='page number for paginated results')
        self.reqparse.add_argument(name='items_per_page',
                                   type=int,
                                   required=False,
                                   default=10,
                                   help='items per page for paginated results')
        
        # filters
        self.reqparse.add_argument(name='type',
                                   type=str,
                                   required=False,
                                   action='append',
                                   help='missing type to filter results')
        self.reqparse.add_argument(name='author',
                                   type=str,
                                   required=False,
                                   action='append',
                                   help='missing author to filter results')
        self.reqparse.add_argument(name='organization',
                                   type=str,
                                   required=False,
                                   default='',
                                   action='append',
                                   help='missing organization to filter results')
        self.reqparse.add_argument(name='owner',
                                   type=str,
                                   required=False,
                                   action='append',
                                   help='missing owner to filter results')
        self.reqparse.add_argument(name='badge_id',
                                   type=int,
                                   required=False,
                                   action='append',
                                   help='badge IDs to search for')
        self.reqparse.add_argument(name='category',
                                   type=str,
                                   required=False,
                                   default='',
                                   action='append',
                                   help='missing category to filter results')

        super(ArtifactSearchIndexAPI, self).__init__()


    @staticmethod
    def is_artifact_type_valid(artifact_type):
        return artifact_type in ARTIFACT_TYPES

    def get(self):
        args = self.reqparse.parse_args()
        keywords = args['keywords']
        page_num = args['page']
        items_per_page = args['items_per_page']

        # artifact search filters
        artifact_types = args['type']
        author_keywords = args['author']
        organization = args['organization']
        owner_keywords = args['owner']
        badge_id_list = args['badge_id']
        category = args['category']
        # sanity checks
        if artifact_types:
            for a_type in artifact_types:
                if not ArtifactSearchIndexAPI.is_artifact_type_valid(a_type):
                    string = ' '.join(ARTIFACT_TYPES)
                    abort(400, description='invalid artifact type passed' + string + ' got '+a_type)

        try:
            stats_search = StatsSearches(
                    search_term=keywords
            )
            db.session.add(stats_search)
            db.session.commit()
        except exc.SQLAlchemyError as error:
            LOG.exception(f'Failed to log search term in the database. Error: {error}')

        result = search_artifacts(keywords, artifact_types, author_keywords, organization, owner_keywords, badge_id_list, page_num, items_per_page, category, groupByCategory=False)
        response = jsonify(result)
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.status_code = 200
        return response

class ArtifactRecommendationAPI(Resource):
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument(name='page',
                                   type=int,
                                   required=False,
                                   default=1,
                                   help='page number for paginated results')
        

        super(ArtifactRecommendationAPI, self).__init__()
    
    def get(self, artifact_group_id, artifact_id):
        verify_api_key(request)
        login_session = verify_token(request)
        args = self.reqparse.parse_args()
        page_num = args['page']

        # check for valid artifact id
        artifact = db.session.query(Artifact).filter(
            Artifact.id == artifact_id).filter(
            Artifact.artifact_group_id == artifact_group_id).first()
        if not artifact:
            abort(400, description='invalid artifact ID')

        authors_res = db.session.query(ArtifactAffiliation, Person.name).filter(ArtifactAffiliation.artifact_id == artifact_id).join(Affiliation,Affiliation.id == ArtifactAffiliation.affiliation_id).join(Person, Affiliation.person_id == Person.id).all()

        #Authors of artifact for later
        authors = [res.name for res in authors_res]

    
        top_keywords = db.session.query(ArtifactTag.tag).filter(
            ArtifactTag.artifact_id == artifact_id, ArtifactTag.source.like('%keywords%')).all()
        if not top_keywords:
            response = jsonify({
                "artifacts": {
                    "total": 0, "page": 1, "pages": 1, "artifacts": []
                }, "avg_rating": None, "num_ratings": 0, "authors": []})
        else:
            keywords = [result.tag for result in top_keywords]
            artifacts = search_artifacts(keywords=" or ".join(keywords), artifact_types = ARTIFACT_TYPES, page_num = page_num, items_per_page= 10, author_keywords = None,  organization = None, owner_keywords = None, badge_id_list = None)
            res =  db.session.query(ArtifactRatings.artifact_id, func.count(ArtifactRatings.id).label('num_ratings'), func.avg(ArtifactRatings.rating).label('avg_rating')).group_by("artifact_id").filter(ArtifactRatings.artifact_id == artifact_id).first()
            if res:
                num_ratings = res.num_ratings if res.num_ratings else 0
                avg_rating = round(res.avg_rating,2) if res.avg_rating else None
            else:
                num_ratings = 0
                avg_rating = None
            response = jsonify({"artifacts": artifacts, "avg_rating": float(avg_rating) if avg_rating else None, "num_ratings": num_ratings, "authors": authors})



        response.headers.add('Access-Control-Allow-Origin', '*')
        response.status_code = 200
        return response
    
class ArtifactCategoryAPI(Resource):
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument(name='keywords',
                                   type=str,
                                   required=False,
                                   help='missing keywords in query string')
        self.reqparse.add_argument(name='page',
                                   type=int,
                                   required=False,
                                   default=1,
                                   help='page number for paginated results')
        self.reqparse.add_argument(name='items_per_page',
                                   type=int,
                                   required=False,
                                   default=10,
                                   help='items per page for paginated results')
        
        # filters
        self.reqparse.add_argument(name='type',
                                   type=str,
                                   required=False,
                                   action='append',
                                   help='missing type to filter results')
        self.reqparse.add_argument(name='author',
                                   type=str,
                                   required=False,
                                   action='append',
                                   help='missing author to filter results')
        self.reqparse.add_argument(name='organization',
                                   type=str,
                                   required=False,
                                   default='',
                                   action='append',
                                   help='missing organization to filter results')
        self.reqparse.add_argument(name='owner',
                                   type=str,
                                   required=False,
                                   action='append',
                                   help='missing owner to filter results')
        self.reqparse.add_argument(name='badge_id',
                                   type=int,
                                   required=False,
                                   action='append',
                                   help='badge IDs to search for')
        self.reqparse.add_argument(name='category',
                                   type=str,
                                   required=False,
                                   default='',
                                   action='append',
                                   help='missing category to filter results')

        super(ArtifactCategoryAPI, self).__init__()


    @staticmethod
    def is_artifact_type_valid(artifact_type):
        return artifact_type in ARTIFACT_TYPES

    def get(self):
        args = self.reqparse.parse_args()
        keywords = args['keywords']
        page_num = args['page']
        items_per_page = args['items_per_page']

        # artifact search filters
        artifact_types = args['type']
        author_keywords = args['author']
        organization = args['organization']
        owner_keywords = args['owner']
        badge_id_list = args['badge_id']
        category = args['category']
        # sanity checks
        if artifact_types:
            for a_type in artifact_types:
                if not ArtifactSearchIndexAPI.is_artifact_type_valid(a_type):
                    string = ' '.join(ARTIFACT_TYPES)
                    abort(400, description='invalid artifact type passed' + string + ' got '+a_type)

        if keywords is None:
            keywords = ''

        try:
            stats_search = StatsSearches(
                    search_term=keywords
            )
            db.session.add(stats_search)
            db.session.commit()
        except exc.SQLAlchemyError as error:
            db.session.rollback()
            LOG.exception(f'Failed to log search term in the database. Error: {error}')
        finally:
            db.session.close() 

        result = search_artifacts(keywords, artifact_types, author_keywords, organization, owner_keywords, badge_id_list, page_num, items_per_page, category, groupByCategory=True)
        response = jsonify(result)
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.status_code = 200
        return response
