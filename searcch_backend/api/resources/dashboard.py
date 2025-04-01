# logic for /rating

from searcch_backend.api.app import db, config_name
from searcch_backend.api.common.auth import (verify_api_key, verify_token)
from searcch_backend.api.resources.favorite import subquery_constructs
from searcch_backend.models.model import *
from searcch_backend.models.schema import *
from flask import abort, jsonify, request, url_for
from flask_restful import reqparse, Resource
from sqlalchemy import func, desc, sql, or_, nullslast
import logging
import base64
from antAPI.client.auth import AntAPIClientAuthenticator
from antAPI.client.trac import (
       antapi_trac_ticket_status,
)
from searcch_backend.api.ticket_creation.antapi_client_conf import AUTH
from collections import defaultdict
LOG = logging.getLogger(__name__)

class UserDashboardAPI(Resource):
    """ 
    UserDashboardAPI
    API to: 
        - generate the dashboard content specific to the current logged-in user

    Dashboard contains:
        - artifacts owned by the user
        - reviews and ratings provided by the user
        - past searches made by the user
        - Comments provided by the user
        - User favorites
    """
    @staticmethod
    def generate_artifact_uri(artifact_group_id, artifact_id=None):
        return url_for('api.artifact', artifact_group_id, artifact_id=artifact_id)
    def get_released_artifacts(self, query_results):
        """
        Filter query results to only include artifacts that have been released.
        
        Args:
            query_results: Results from the SQLAlchemy query containing artifact and ticket information
        
        Returns:
            List of artifacts that have been released
        """
        released_artifacts = []
        LOG.error(f"query_results: {query_results}")
        for result in query_results:
            ticket_id = result.ticket_id
            ticket_status = None
            
            if ticket_id == -1:
                ticket_status = "released"
            elif ticket_id == -2:
                ticket_status = "new"
            else:
                auth = AntAPIClientAuthenticator(**AUTH)
                try:
                    ticket_status = antapi_trac_ticket_status(auth, ticket_id)
                    LOG.error(f"Ticket status: {ticket_status} - {ticket_id}")
                except Exception as err:
                    LOG.error(f"Ticket status fetch for ticket ID {ticket_id} unsuccessful: {str(err)}")
                    ticket_status = None
                    
                # Handle cancelled or non-existent tickets
                if (ticket_status.lower() == "cancelled"):
                    # Delete the request
                    db.session.query(ArtifactRequests).filter(
                        ArtifactRequests.artifact_group_id == result.artifact_group_id,
                        ArtifactRequests.requester_user_id == result.requester_user_id
                    ).delete()
                    db.session.commit()
                    ticket_status = "unrequested"
            
            # If the ticket is released, add it to our results
            if ticket_status.lower() == "released":
                released_artifacts.append({
                    'artifact_id': result.id,
                    'requester_user_id': result.requester_user_id,
                    'requester_name': result.requester_name,
                    'requester_email': result.requester_email,
                    'requester_position': result.requester_position,
                    'requester_organizations': result.requester_organizations,
                    'ticket_id': ticket_id
                })
        
        return released_artifacts
    def get(self):
        verify_api_key(request)
        login_session = verify_token(request)

        #logged in user record
        user = db.session.query(User).filter(User.id == login_session.user_id).first()
        
        # artifacts owned by the logged-in user
        artifact_schema = ArtifactSchema(many=True, only=('artifact_group_id', 'id', 'type', 'title', 'ctime'))
        contributed_artifacts = db.session.query(Artifact)\
            .join(ContributedArtifacts, func.trim(ContributedArtifacts.title) == func.trim(Artifact.title))\
            .filter(ContributedArtifacts.user_id == login_session.user_id)
        contributed_artifacts = artifact_schema.dump(contributed_artifacts)
        given_ratings = db.session.query(ArtifactRatings.artifact_group_id, ArtifactRatings.rating, Artifact.title, Artifact.type)\
            .join(ArtifactGroup, ArtifactGroup.id == ArtifactRatings.artifact_group_id)\
            .join(ArtifactPublication, ArtifactPublication.id == ArtifactGroup.publication_id)\
            .join(Artifact, Artifact.id == ArtifactPublication.artifact_id)\
            .filter(ArtifactRatings.user_id == login_session.user_id)\
            .all()
        artifact_requests = db.session.query(ArtifactRequests.artifact_group_id, ArtifactRequests.ticket_id, Artifact.title, Artifact.type, ArtifactRequests.agreement_file)\
            .join(ArtifactGroup, ArtifactGroup.id == ArtifactRequests.artifact_group_id)\
            .join(ArtifactPublication, ArtifactPublication.id == ArtifactGroup.publication_id)\
            .join(Artifact, Artifact.id == ArtifactPublication.artifact_id)\
            .filter(ArtifactRequests.requester_user_id == login_session.user_id)\
            .all()

        contributed_with_requests_query = db.session.query(
            Artifact.id,
            ArtifactRequests.requester_user_id,
            ArtifactRequests.ticket_id,  
            Person.name.label('requester_name'),
            Person.email.label('requester_email'),
            Person.position.label('requester_position'),
            func.array_agg(Organization.name).label('requester_organizations'),
        ).join(ContributedArtifacts, func.trim(ContributedArtifacts.title) == func.trim(Artifact.title)
        ).join(ArtifactRequests, Artifact.artifact_group_id == ArtifactRequests.artifact_group_id
        ).join(User, ArtifactRequests.requester_user_id == User.id
        ).join(Person, User.person_id == Person.id
        ).join(UserAffiliation, User.id == UserAffiliation.user_id
        ).join(Organization, UserAffiliation.org_id == Organization.id
        ).filter(ContributedArtifacts.user_id == login_session.user_id
        ).group_by(Artifact.id, ArtifactRequests.requester_user_id, ArtifactRequests.ticket_id, Person.name, Person.email, Person.position)

        contributed_with_requests_results = contributed_with_requests_query.all()
        released_artifacts_all_data = self.get_released_artifacts(contributed_with_requests_results)
        # Data for artifact contributors: Add list of users to whom the artifact was released for each artifact in contributed_artifacts
        artifact_requesters = defaultdict(list)
        for row in released_artifacts_all_data:
            artifact_id = row['artifact_id'] 
            artifact_requesters[artifact_id].append({
                'requester_name': row['requester_name']  ,
                'requester_email': row['requester_email'],
                'requester_position': row['requester_position'],
                'requester_organizations': row['requester_organizations'],
            })
        for artifact in contributed_artifacts:
            artifact['users'] = [user['requester_name'] for user in artifact_requesters.get(artifact['id'], [])]

        # Data for artifact contributors: Get information regarding the number of artifacts released, number of users released to and set of names of all users released to
        users_released_to = {}
        for datum in released_artifacts_all_data:
            if datum['requester_name'] not in users_released_to:
                users_released_to[datum['requester_name']] = {
                    'requester_email': datum['requester_email'],
                    'requester_position': datum['requester_position'],
                    'requester_organizations': datum['requester_organizations'],
                }
        released_artifacts_overview = {
            'total_number_released': len(released_artifacts_all_data),
            'total_number_users_released_to': len(users_released_to),
            'users_released_to': users_released_to
        }
        
        rated_artifacts = [] 
        for artifact in given_ratings:
            result = {
                "artifact_group_id": artifact.artifact_group_id,
                "rating": artifact.rating,
                "title": artifact.title,
                "type": artifact.type
            }
            rated_artifacts.append(result)

        requested_artifacts = [] 
        for artifact in artifact_requests:
            encoded_agreement_file = base64.b64encode(artifact.agreement_file).decode('utf-8') if artifact.agreement_file else None
            result = {
                "artifact_group_id": artifact.artifact_group_id,
                "ticket_id": artifact.ticket_id,
                "title": artifact.title,
                "type": artifact.type,
                "agreement_file":encoded_agreement_file
            }
            requested_artifacts.append(result)

        response = jsonify({
            "contributor_id": login_session.user_id,
            "contributed_artifacts": contributed_artifacts,
            "requested_artifacts": requested_artifacts,
            "released_artifacts_overview": released_artifacts_overview,
            "given_ratings": rated_artifacts
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.status_code = 200
        return response

class ArtifactStatsAPI(Resource):
    """ 
    ArtifactStatsAPI
    API to: 
        - generate artifact stats and rank based on them

    Dashboard contains:
        - Average rating of artifact
        - No of ratings on an artifact
        - No of reviews on artifact
        - Order by average rating
    """

    def get(self):
        verify_api_key(request)
        login_session = verify_token(request)

        # Rating and review stats
        sqratings, sqreviews = subquery_constructs()

        artifact_list = db.session.query(Artifact, 'num_ratings', 'avg_rating', 'num_reviews'
                                                ).join(sqratings, Artifact.id == sqratings.c.artifact_id, isouter=True
                                                ).join(sqreviews, Artifact.id == sqreviews.c.artifact_id, isouter=True
                                                ).filter(or_(sqratings.c.num_ratings > 0, sqreviews.c.num_reviews > 10)
                                                ).order_by(sqratings.c.avg_rating.desc().nullslast(),sqreviews.c.num_reviews.desc()
                                                ).all()

        ranked_artifacts = []
        
        for artifact, num_ratings, avg_rating, num_reviews in artifact_list:
            result = {
                "id": artifact.id,
                "uri": UserDashboardAPI.generate_artifact_uri(artifact.artifact_group_id, artifact_id=artifact.id),
                "doi": artifact.url,
                "type": artifact.type,
                "title": artifact.title,
                "description": artifact.description,                
                "avg_rating": float(avg_rating) if avg_rating else None,
                "num_ratings": num_ratings if num_ratings else 0,
                "num_reviews": num_reviews if num_reviews else 0
            }
            ranked_artifacts.append(result)

        response = jsonify({
            "ranked_artifacts": ranked_artifacts
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.status_code = 200
        return response
