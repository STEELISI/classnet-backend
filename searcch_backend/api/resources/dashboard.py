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

    def get(self):
        verify_api_key(request)
        login_session = verify_token(request)

        #logged in user record
        user = db.session.query(User).filter(User.id == login_session.user_id).first()
        
        # artifacts owned by the logged-in user
        artifact_schema = ArtifactSchema(many=True, only=('artifact_group_id', 'id', 'type', 'title', 'ctime'))
        owned_artifacts = db.session.query(Artifact)\
            .join(ContributedArtifacts, func.trim(ContributedArtifacts.title) == func.trim(Artifact.title))\
            .filter(ContributedArtifacts.user_id == login_session.user_id)
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
            "owned_artifacts": artifact_schema.dump(owned_artifacts),
            "requested_artifacts": requested_artifacts,
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
