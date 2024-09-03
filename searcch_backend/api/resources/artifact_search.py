# logic for /artifacts

from searcch_backend.api.app import db
from searcch_backend.models.model import *
from searcch_backend.models.schema import *
from flask import abort, jsonify, url_for, request
from flask_restful import reqparse, Resource
from sqlalchemy import func, desc, or_, case, exc, and_
from searcch_backend.api.common.auth import (verify_api_key, has_api_key, has_token, verify_token)
import math
import logging
import json
import re
from sqlalchemy.dialects import postgresql

LOG = logging.getLogger(__name__)

def generate_artifact_uri(artifact_group_id, artifact_id=None):
    return url_for('api.artifact', artifact_group_id=artifact_group_id,
                   artifact_id=artifact_id)

def search_artifacts(keywords, artifact_types, author_keywords, organization, owner_keywords, badge_id_list, page_num, items_per_page, category):
    """ search for artifacts based on keywords, with optional filters by owner and affiliation """
    sqratings = db.session.query(
        ArtifactRatings.artifact_group_id,
        func.count(ArtifactRatings.id).label('num_ratings'),
        func.avg(ArtifactRatings.rating).label('avg_rating')
    ).group_by(ArtifactRatings.artifact_group_id).subquery()

    sqreviews = db.session.query(
        ArtifactReviews.artifact_group_id,
        func.count(ArtifactReviews.id).label('num_reviews')
    ).group_by(ArtifactReviews.artifact_group_id).subquery()

    # Subquery to aggregate tags
    tag_aggregation = db.session.query(
        Artifact.id.label('artifact_id'),
        func.string_agg(ArtifactTag.tag, ' ').label('tags')
    ).outerjoin(ArtifactTag, ArtifactTag.artifact_id == Artifact.id).group_by(Artifact.id).subquery()

    # Base query
    query = db.session.query(
        Artifact,
        tag_aggregation.c.tags,
        sqratings.c.num_ratings,
        sqratings.c.avg_rating,
        sqreviews.c.num_reviews,
        StatsArtifactViews.view_count,
        DUA.dua_url,
        ArtifactGroup.owner_id
    ).outerjoin(ArtifactGroup, ArtifactGroup.id == Artifact.artifact_group_id
    ).outerjoin(sqratings, ArtifactGroup.id == sqratings.c.artifact_group_id
    ).outerjoin(ArtifactPublication, ArtifactPublication.id == ArtifactGroup.publication_id
    ).outerjoin(sqreviews, ArtifactGroup.id == sqreviews.c.artifact_group_id
    ).outerjoin(StatsArtifactViews, Artifact.artifact_group_id == StatsArtifactViews.artifact_group_id
    ).join(DUA, and_(Artifact.collection == DUA.collection, Artifact.provider == DUA.provider)
    ).outerjoin(tag_aggregation, tag_aggregation.c.artifact_id == Artifact.id
    ).filter(ArtifactPublication.id != None).group_by(
        Artifact.id,
        tag_aggregation.c.tags,
        sqratings.c.num_ratings,
        sqratings.c.avg_rating,
        sqreviews.c.num_reviews,
        StatsArtifactViews.view_count,
        DUA.dua_url,
        ArtifactGroup.owner_id
    )

    if keywords:
        # Create the tsvector dynamically and filter with plainto_tsquery, including tags
        tsvector = func.to_tsvector('english', Artifact.title + ' ' + Artifact.shortdesc + ' ' + func.coalesce(tag_aggregation.c.tags, ''))
        tsquery = func.to_tsquery('english', ' | '.join(keywords.split()))
        query = query.filter(tsvector.op('@@')(tsquery))
        
        # Count keyword occurrences in title, tags, short desc
        keyword_counts_title = [func.strpos(func.lower(Artifact.title), func.lower(keyword)) for keyword in keywords.split()]
        keyword_counts_tags = [func.strpos(func.lower(tag_aggregation.c.tags), func.lower(keyword)) for keyword in keywords.split()]
        keyword_counts_desc = [func.strpos(func.lower(Artifact.shortdesc), func.lower(keyword)) for keyword in keywords.split()]

        #Setting weight for different matches
        title_match_weight = 3
        tags_match_weight = 1.5
        description_match_weight = 0.75

        keyword_count_title = sum([case([(kc > 0, title_match_weight)], else_=0) for kc in keyword_counts_title])
        keyword_count_tags = sum([case([(kc > 0, tags_match_weight)], else_=0) for kc in keyword_counts_tags])
        keyword_count_desc = sum([case([(kc > 0, description_match_weight)], else_=0) for kc in keyword_counts_desc])
        
        total_keyword_count = keyword_count_title + keyword_count_tags + keyword_count_desc

        #Ordering based on total keyword score and tiltes date
        query = query.add_columns(total_keyword_count.label('keyword_count_score'))
        query = query.order_by(desc('keyword_count_score'), desc(func.right(Artifact.title, 8)), Artifact.title)

    else:
        #Ordering on last 8 characters in title (Date)
        query = query.order_by(desc(func.right(Artifact.title, 8)), Artifact.title)

    if author_keywords or organization or category:
        if author_keywords:
            if type(author_keywords) is list:
                author_keywords = ' or '.join(author_keywords)
            query = query.join(Person, Person.id == Artifact.owner_id
            ).filter(Person.person_tsv.op('@@')(func.plainto_tsquery("english", author_keywords)))

        if organization:
            if type(organization) is list:
                query = query.filter(Artifact.provider.in_(organization))
            else:
                query = query.filter(Artifact.provider == organization)

        if category:
            if type(category) is list:
                query = query.filter(Artifact.category.in_(category))
            else:
                query = query.filter(Artifact.category == category)

    if owner_keywords:
        if type(owner_keywords) is list:
            owner_keywords = ' or '.join(owner_keywords)
        query = query.join(Person, Artifact.owner_id == Person.id
        ).filter(Person.person_tsv.op('@@')(func.plainto_tsquery("english", owner_keywords)))


    if badge_id_list:
        query = query.join(ArtifactBadge, Artifact.id == ArtifactBadge.artifact_id
        ).filter(ArtifactBadge.badge_id.in_(badge_id_list))

    if artifact_types:
        if len(artifact_types) > 1:
            query = query.filter(or_(Artifact.type == a_type for a_type in artifact_types))
        else:
            query = query.filter(Artifact.type == artifact_types[0])

    # Categorize artifacts from query results, counting and storing their titles in a dictionary by category
    categoryDict = {}
    for row in query.all():
        if keywords:
            artifact, _, num_ratings,avg_rating,num_reviews,view_count,dua_url, owner_id, _ = row
        else:
            artifact, _, num_ratings, avg_rating, num_reviews, view_count, dua_url, owner_id = row
        if artifact.category not in categoryDict:
            categoryDict[artifact.category] = dict(count=0, artifacts=[])
        categoryDict[artifact.category]["count"] += 1
        categoryDict[artifact.category]["artifacts"].append(artifact.title)

    #Fetching results based on page number
    total_results = query.count()
    artifacts = query.offset((page_num - 1) * items_per_page).limit(items_per_page).all()

    result_artifacts = []
    for row in artifacts:
        if keywords:
            artifact, _, num_ratings, avg_rating, num_reviews, view_count, dua_url, owner_id , _ =  row
        else:
            artifact, _, num_ratings, avg_rating, num_reviews, view_count, dua_url, owner_id = row
        result_artifacts.append({
            "id": artifact.id,
            "artifact_group_id": artifact.artifact_group_id,
            "artifact_group": {
                "id": artifact.artifact_group_id,
                "owner_id": owner_id
            },
            "uri": generate_artifact_uri(artifact.artifact_group_id, artifact_id=artifact.id),
            "doi": artifact.url,
            "type": artifact.type,
            "title": artifact.title,
            "description": artifact.description,
            "avg_rating": float(avg_rating) if avg_rating else None,
            "num_ratings": num_ratings if num_ratings else 0,
            "num_reviews": num_reviews if num_reviews else 0,
            "owner": {"id": artifact.owner.id},
            "views": view_count if view_count else 0,
            "dua_url": dua_url,
            "category": artifact.category,
            "shortdesc": artifact.shortdesc
        })

    artifact_dict = dict(
        page=page_num,
        total=total_results,
        pages=int(math.ceil(total_results / items_per_page)),
        artifacts=result_artifacts
    )
    return dict(category_dict = categoryDict, artifact_dict = artifact_dict)

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
        if keywords:
            pattern = r'^[a-zA-Z0-9][a-zA-Z0-9-_ ]*$'
            regex = re.compile(pattern)
            if regex.match(keywords) is None:
                abort(401, description="Invalid input. Only letters, digits, dashes, underscores, and spaces are allowed, and it must start with a letter or digit.")
        page_num = args['page']
        items_per_page = args['items_per_page']

        # artifact search filters
        artifact_types = args['type']
        author_keywords = args['author']
        organization = args['organization']
        owner_keywords = args['owner']
        badge_id_list = args['badge_id']
        category = args['category']
        LOG.error(f'Organization val = {organization}')
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
        # finally:
        #     db.session.close() 

        result = search_artifacts(keywords, artifact_types, author_keywords, organization, owner_keywords, badge_id_list, page_num, items_per_page, category)
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