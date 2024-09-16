'''logic for /artifacts'''

import logging
import json
import os
import time
from flask import abort, jsonify, request
from flask_restful import reqparse, Resource
from sqlalchemy import func, desc, and_
from searcch_backend.api.app import db
from searcch_backend.models.model import (
    Artifact,
    ArtifactGroup,
    ArtifactRequests,
    ArtifactRatings,
    ArtifactReviews,
    ArtifactPublication,
    Person
)
from searcch_backend.models.schema import (
    ArtifactSchema,
    ArtifactRequestSchema,
    ArtifactRatingsSchema,
    ArtifactReviewsSchema,
)
from searcch_backend.api.common.stats import StatsResource
from antAPI.client.auth import AntAPIClientAuthenticator
from antAPI.client.trac import (
   antapi_trac_ticket_new, antapi_trac_ticket_attach
)
from searcch_backend.api.common.auth import (
    verify_api_key,
    has_api_key,
    has_token,
    verify_token,
)
from searcch_backend.api.ticket_creation.antapi_client_conf import AUTH


LOG = logging.getLogger(__name__)
TEST_PROJECT_NAME = "Test-Nosubmit"

class ArtifactRequestAPI(Resource):
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        super().__init__()

    def get(self, artifact_group_id, artifact_id=None):
        if has_api_key(request):
            verify_api_key(request)

        # Verify the group exists
        artifact_group = db.session.query(ArtifactGroup).filter(
            ArtifactGroup.id == artifact_group_id).first()
        if not artifact_group:
            abort(404, description="nonexistent artifact group")

        #
        # Determine which artifact record to return.
        #
        # If the artifact_id is not specified, there must be a publication
        # record for the group, unless: 1) caller is owner and has a draft; 2)
        # caller is admin and gets the most recent draft.  I do not like this
        # because it might be confusing, but we have to do it because a user
        # can add a relationship to an unpublished artifact (and
        # favorite/review/rate it), and we don't want to break the frontend for
        # the user or admins.
        #
        # If the artifact_id is specified, and if it is published, anyone can
        # retrieve it.  If not published, only the owner of the group or of the
        # artifact, or an admin, may retrieve it.
        #
        artifact = None
        if not artifact_id:
            if not artifact_group.publication:
                login_session = None
                if has_token(request):
                    login_session = verify_token(request)
                if not (login_session
                        and (login_session.user_id == artifact_group.owner_id
                             or login_session.is_admin)):
                    abort(400, description="insufficient permission to access unpublished artifact")
                # Find the most recent owner draft
                artifact = db.session.query(Artifact)\
                  .filter(Artifact.artifact_group_id == artifact_group_id)\
                  .filter(Artifact.owner_id == artifact_group.owner_id)\
                  .order_by(desc(Artifact.ctime))\
                  .first()
            else:
                artifact = artifact_group.publication.artifact
        else:
            res = db.session.query(Artifact, ArtifactPublication)\
              .join(ArtifactPublication, ArtifactPublication.artifact_id == Artifact.id, isouter=True)\
              .filter(and_(Artifact.id == artifact_id,Artifact.artifact_group_id == artifact_group_id))\
              .first()
            if not res:
                abort(404, description="no such artifact")
            (artifact, publication) = res
            if not artifact:
                abort(404, description="no such artifact")
            if not publication:
                login_session = None
                if has_token(request):
                    login_session = verify_token(request)
                if not (login_session
                        and (login_session.user_id == artifact_group.owner_id
                             or login_session.user_id == artifact.owner_id
                             or login_session.is_admin)):
                    abort(400, description="insufficient permission to access artifact")

        # get average rating for the artifact, number of ratings
        rating_aggregates = db.session.query(ArtifactRatings.artifact_group_id, func.count(ArtifactRatings.id).label('num_ratings'), func.avg(
            ArtifactRatings.rating).label('avg_rating')).filter(ArtifactRatings.artifact_group_id == artifact_group.id).group_by("artifact_group_id").all()

        ratings = db.session.query(ArtifactRatings, ArtifactReviews).join(ArtifactReviews, and_(
            ArtifactRatings.user_id == ArtifactReviews.user_id,
            ArtifactRatings.artifact_group_id == ArtifactReviews.artifact_group_id
        )).filter(ArtifactRatings.artifact_group_id == artifact_group.id).all()

        # Record Artifact view in database
        # XXX: need to handle API-only case.
        session_id = request.cookies.get('session_id')
        if session_id:
            stat_view_obj = StatsResource(artifact_group_id=artifact_group_id, session_id=session_id)
            stat_view_obj.recordView()

        response = jsonify({
            "artifact": ArtifactSchema().dump(artifact),
            "avg_rating": float(rating_aggregates[0][2]) if rating_aggregates else None,
            "num_ratings": rating_aggregates[0][1] if rating_aggregates else 0,
            "num_reviews": len(ratings) if ratings else 0,
            "rating_review": [{
                "rating": ArtifactRatingsSchema(only=("rating",)).dump(rating),
                "review": ArtifactReviewsSchema(exclude=("artifact_group_id", "user_id")).dump(review)
                } for rating, review in ratings]
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.status_code = 200
        return response

    def post(self, artifact_group_id, artifact_id=None):
        if has_api_key(request):
            verify_api_key(request)

        self.reqparse.parse_args()

        # Verify the group exists
        artifact_group = db.session.query(ArtifactGroup).filter(
            ArtifactGroup.id == artifact_group_id).first()
        if not artifact_group:
            abort(404, description="nonexistent artifact group")

        # Verify the artifact exists
        if artifact_id:
            artifact = db.session.query(Artifact).filter(
                Artifact.id == artifact_id).first()
            if not artifact:
                abort(404, description="nonexistent artifact")

        # Verify the user is the owner of the artifact group
        login_session = None
        if has_token(request):
            login_session = verify_token(request)
        if not login_session:
            abort(400, description="insufficient permission to access unpublished artifact")

        # Verify if user has already submitted a request
        artifact_request = db.session.query(ArtifactRequests).filter(
                ArtifactRequests.artifact_group_id == artifact_group_id,
                ArtifactRequests.requester_user_id == login_session.user_id
            ).first()
        if artifact_request:
            response = jsonify({
                "status": 1,
                "error": "User has already submitted a request for this artifact"
            })
        else:
            user_id = login_session.user_id
            requester_ip_addr = request.headers.get('X-Forwarded-For', request.remote_addr)

            project = request.form.get('project')
            if not project:
                abort(400, description="missing project")
            project_description = request.form.get('project_description')
            if not project_description:
                abort(400, description="missing project_description")
            researchers = request.form.get('researchers')
            if not researchers:
                abort(400, description="missing researchers object")
            representative_researcher_email = request.form.get('representative_researcher_email')
            if not representative_researcher_email:
                abort(400, description="missing representative researcher email")
            agreement_file = request.files.get('file')
            if not agreement_file:
                abort(400, description="missing agreement file")
            agreement_file = agreement_file.read()

            irb_file = request.files.get('pdf_file')
            if not irb_file:
                irb_file = None
            else:
                irb_file = irb_file.read()
            frgpData = request.form.get('frgpData')
            if not frgpData:
                frgpData = None


            agreement_file_folder = './agreement_file_folder'
            if not os.path.exists(agreement_file_folder):
                os.makedirs(agreement_file_folder)

            # The filename below is unique since this else block can only be accessed once
            # for a given (artifact_group_id,user_id) pair
            filename = (agreement_file_folder
                        + f'/signed_dua_artifact_group_id_{artifact_group_id}'
                        + f'_requester_user_id_{user_id}.html'
            )
            with open(filename, 'wb+') as fout:
                fout.write(agreement_file)

            dataset = request.form.get('dataset')
            if not dataset:
                abort(400, description="missing dataset")

            request_entry = ArtifactRequests(
                artifact_group_id=artifact_group_id,
                requester_user_id=user_id,
                project=project,
                project_description=project_description,
                researchers=researchers,
                representative_researcher_email=representative_researcher_email,
                agreement_file=agreement_file,
                irb=irb_file,
                frgp_data=frgpData
            )
            # create a record now, so we can get it's id and submit it in a ticket
            # if ticket creation fails, we'll have to undo this add
            db.session.add(request_entry)
            db.session.commit()
            artifact_request_id = request_entry.id

            researchers = json.loads(researchers)
            artifact_timestamp = str(time.time())
            representative_researcher = researchers[0]
            for researcher in researchers:
                if researcher['email'] == representative_researcher_email:
                    representative_researcher = researcher

            params = dict(
                project=project,
                project_description=project_description,
                project_justification=request.form.get('project_justification', ''),
                datasets=dataset,
                affiliation=representative_researcher['organization'],
                artifact_request_id=artifact_request_id,
                artifact_timestamp=artifact_timestamp,
                requester_ip_addr=requester_ip_addr
            )
            for index,researcher in enumerate(researchers):
                params['researcher_'+str(index+1)] = researcher['name']
                params['researcher_email_'+str(index+1)] = researcher['email']


            # Create a ticket for the artifact request
            
            # For testing purposes we do not create a request to the ANT backend if project name is TEST_PROJECT_NAME
            if project == TEST_PROJECT_NAME:
                # We know that ticket_id cannot be -1 so we use that as the dummy ticket_id value
                # in the case where we want to test the requested and released ticket flow
                request_entry.ticket_id = -1
                ticket_id = -1
            elif project == TEST_PROJECT_NAME+"-2":
                 # We know that ticket_id cannot be -2 so we use that as the dummy ticket_id value
                 # in the case where we want to test the requested but not released ticket flow
                request_entry.ticket_id = -2
                ticket_id = -2
            else:
                # Regular user flow
                ticket_description = "=== What Datasets\n{datasets}\n\n=== Why these Datasets\n{project_justification}\n\n=== What Project\n{project}\n\n=== Project Description\n{project_description}\n\n=== Researchers\n"
                for index,researcher in enumerate(researchers):
                    ticket_description+="{researcher_"+str(index+1)+"} (@{researcher_email_"+str(index+1)+"})\n"

                ticket_description+="\n=== Researcher Affiliation\n{affiliation}\n\n=== Comunda Info\n||= request_id =|| {artifact_request_id} ||\n||= timestamp  =|| {artifact_timestamp} ||\n||= ip address =|| {requester_ip_addr} ||"
                ticket_description=ticket_description.format(**params)
                ticket_fields = dict(
                    description=ticket_description,
                    researcher=representative_researcher['name'],
                    email=representative_researcher['email'],
                    affiliation=representative_researcher['organization'],
                    datasets=dataset,
                    ssh_key=representative_researcher.get('publicKey', ''),
                )

                error_response = jsonify({
                    "status": 500,
                    "status_code": 500,
                    "message": "Request could not be submitted due to a server error, please try again after sometime.",
                })
                error_response.headers.add('Access-Control-Allow-Origin', '*')

                try:
                    auth = AntAPIClientAuthenticator(**AUTH)
                    ticket_id = int(antapi_trac_ticket_new(auth, **ticket_fields))
                    antapi_trac_ticket_attach(auth, ticket_id, [filename])

                except Exception as err: # pylint: disable=broad-except
                    # undo the previous add
                    LOG.error(f"Failed to create ticket: {err}")
                    try:
                        db.session.delete(request_entry)
                    except Exception as err: # pylint: disable=broad-except
                        LOG.error(f"Can't undo entry for a failed ticket add id={request_entry.id}: {err}")
                    return error_response
            try:
                db.session.query(ArtifactRequests) \
                    .filter(artifact_request_id == ArtifactRequests.id) \
                    .update({'ticket_id': ticket_id})
                db.session.commit()
            except Exception as err: # pylint: disable=broad-except (we expect to enter this except block if ticket_id was not assigned a value - in which case the request must be deleted since no ticket was assigned for it)
                LOG.error(f"Ticket was created (#{ticket_id}), but db update failed: {str(err)})")
                try:
                    db.session.query(ArtifactRequests).filter(artifact_request_id == ArtifactRequests.id).delete()
                    db.session.commit()
                except Exception as err: # pylint: disable=broad-except
                    LOG.error(f"Cannot delete db record: {str(err)})")
                return error_response

            response = jsonify({
                "status": 0,
                "message": "Request submitted successfully",
                "request": ArtifactRequestSchema().dump(request_entry),
            })

        response.headers.add('Access-Control-Allow-Origin', '*')
        response.status_code = 200
        return response


# This is a separate endpoint used to request a group of artifacts present in the artifact cart
# listOfArtifactIDs is a list of lists where each inner list is of the format [artifact_group_id,artifact_id]
# ANT API takes in a request for an artifact based on its title, so we add a list of titles based on the [artifact_group_id,artifact_id] pairs provided

class ArtifactRequestCartAPI(Resource):
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        super().__init__()
        self.reqparse.add_argument(name='listOfArtifactIDs',
                                   type=str,
                                   required=True,
                                   help='missing listOfArtifactIDs') 
    
    def post(self):
        if has_api_key(request):
            verify_api_key(request)

        args = self.reqparse.parse_args()
        listOfArtifactIDs = args['listOfArtifactIDs']
        if listOfArtifactIDs:
            listOfArtifactIDs = json.loads(listOfArtifactIDs)   
         # Verify the user is the owner of the artifact group
        login_session = None
        if has_token(request):
            login_session = verify_token(request)
        if not login_session:
            abort(400, description="insufficient permission to access unpublished artifact")
        artifact_request_ids = []

        user_id = login_session.user_id
        requester_ip_addr = request.headers.get('X-Forwarded-For', request.remote_addr)

        project = request.form.get('project')
        if not project:
            abort(400, description="missing project")
        project_description = request.form.get('project_description')
        if not project_description:
            abort(400, description="missing project_description")
        researchers = request.form.get('researchers')
        if not researchers:
            abort(400, description="missing researchers object")
        representative_researcher_email = request.form.get('representative_researcher_email')
        if not representative_researcher_email:
            abort(400, description="missing representative researcher email")
        agreement_file = request.files.get('file')
        if not agreement_file:
            abort(400, description="missing agreement file")
        agreement_file = agreement_file.read()

        frgpData = request.form.get('frgpData')
        if not frgpData:
            frgpData = None

        agreement_file_folder = './agreement_file_folder'
        if not os.path.exists(agreement_file_folder):
            os.makedirs(agreement_file_folder)

        # The filename below is unique since this else block can only be accessed once
        # for a given (artifact_group_id,user_id) pair
        filename = (agreement_file_folder
                    + f'/signed_dua_artifact_group_id_{str(listOfArtifactIDs)}'
                    + f'_requester_user_id_{user_id}.html'
        )
        with open(filename, 'wb+') as fout:
            fout.write(agreement_file)

        for index, (artifact_group_id,artifact_id) in enumerate(listOfArtifactIDs):
            # Verify the group exists
            artifact_group = db.session.query(ArtifactGroup).filter(
                ArtifactGroup.id == artifact_group_id).first()
            if not artifact_group:
                abort(404, description="nonexistent artifact group")

            # Verify the artifact exists
            artifact = db.session.query(Artifact).filter(
                Artifact.id == artifact_id).first()
            if not artifact:
                abort(404, description="nonexistent artifact")
             
            irb_file = request.files.get(f'irb_file_{index}', None)
            if irb_file:
                irb_file = irb_file.read()

            # Verify if user has already submitted a request
            artifact_request = db.session.query(ArtifactRequests).filter(
                    ArtifactRequests.artifact_group_id == artifact_group_id,
                    ArtifactRequests.requester_user_id == login_session.user_id
            ).first()

            if artifact_request:
                response = jsonify({
                    "status": 1,
                    "error": "User has already submitted a request for artifact: " +  str(artifact_group_id)
                })
                return response
            else:
                request_entry = ArtifactRequests(
                    artifact_group_id=artifact_group_id,
                    requester_user_id=user_id,
                    project=project,
                    project_description=project_description,
                    researchers=researchers,
                    representative_researcher_email=representative_researcher_email,
                    agreement_file=agreement_file,
                    irb=irb_file,
                    frgp_data=frgpData
                )
                # create a record now, so we can get it's id and submit it in a ticket
                # if ticket creation fails, we'll have to undo this add
                db.session.add(request_entry)
                db.session.commit()
                artifact_request_ids.append(str(request_entry.id))

        researchers = json.loads(researchers)
        artifact_timestamp = str(time.time())
        representative_researcher = researchers[0]
        for researcher in researchers:
            if researcher['email'] == representative_researcher_email:
                representative_researcher = researcher
        datasets = []
        for artifact_group_id,artifact_id in listOfArtifactIDs:
            dataset_name_str = db.session.query(Artifact.title).filter(artifact_group_id == Artifact.artifact_group_id).first()[0]
            datasets.append(dataset_name_str)
        params = dict(
            project=project,
            project_description=project_description,
            project_justification=request.form.get('project_justification', ''),
            datasets=' '.join(datasets),
            affiliation=representative_researcher['organization'],
            artifact_request_id=' '.join(artifact_request_ids),
            artifact_timestamp=artifact_timestamp,
            requester_ip_addr=requester_ip_addr
        )
        for index,researcher in enumerate(researchers):
            params['researcher_'+str(index+1)] = researcher['name']
            params['researcher_email_'+str(index+1)] = researcher['email']

        # Create a ticket for the artifact request
        
        # For testing purposes we do not create a request to the ANT backend if project name is TEST_PROJECT_NAME
        if project == TEST_PROJECT_NAME:
            # We know that ticket_id cannot be -1 so we use that as the dummy ticket_id value
            # in the case where we want to test the requested and released ticket flow
            request_entry.ticket_id = -1
            ticket_id = -1
        elif project == TEST_PROJECT_NAME+"-2":
                # We know that ticket_id cannot be -2 so we use that as the dummy ticket_id value
                # in the case where we want to test the requested but not released ticket flow
            request_entry.ticket_id = -2
            ticket_id = -2
        else:
            # Regular user flow
            ticket_description = "=== What Datasets\n{datasets}\n\n=== Why these Datasets\n{project_justification}\n\n=== What Project\n{project}\n\n=== Project Description\n{project_description}\n\n=== Researchers\n"
            for index,researcher in enumerate(researchers):
                ticket_description+="{researcher_"+str(index+1)+"} (@{researcher_email_"+str(index+1)+"})\n"

            ticket_description+="\n=== Researcher Affiliation\n{affiliation}\n\n=== Comunda Info\n||= request_id =|| {artifact_request_id} ||\n||= timestamp  =|| {artifact_timestamp} ||\n||= ip address =|| {requester_ip_addr} ||"
            ticket_description=ticket_description.format(**params)
            ticket_fields = dict(
                description=ticket_description,
                researcher=representative_researcher['name'],
                email=representative_researcher['email'],
                affiliation=representative_researcher['organization'],
                datasets=' '.join(datasets),
                ssh_key=representative_researcher.get('publicKey', ''),
            )

            error_response = jsonify({
                "status": 500,
                "status_code": 500,
                "message": "Request could not be submitted due to a server error, please try again after sometime.",
            })
            error_response.headers.add('Access-Control-Allow-Origin', '*')

            try:
                auth = AntAPIClientAuthenticator(**AUTH)
                ticket_id = int(antapi_trac_ticket_new(auth, **ticket_fields))
                antapi_trac_ticket_attach(auth, ticket_id, [filename])

            except Exception as err: # pylint: disable=broad-except
                # undo the previous add
                LOG.error(f"Failed to create ticket: {err}")
                try:
                    db.session.delete(request_entry)
                except Exception as err: # pylint: disable=broad-except
                    LOG.error(f"Can't undo entry for a failed ticket add id={request_entry.id}: {err}")
                return error_response
        for artifact_request_id in artifact_request_ids:
            try:
                db.session.query(ArtifactRequests) \
                    .filter(artifact_request_id == ArtifactRequests.id) \
                    .update({'ticket_id': ticket_id})
                db.session.commit()
            except Exception as err: # pylint: disable=broad-except (we expect to enter this except block if ticket_id was not assigned a value - in which case the request must be deleted since no ticket was assigned for it)
                LOG.error(f"Ticket was created (#{ticket_id}), but db update failed: {str(err)})")
                try:
                    db.session.query(ArtifactRequests).filter(artifact_request_id == ArtifactRequests.id).delete()
                    db.session.commit()
                except Exception as err: # pylint: disable=broad-except
                    LOG.error(f"Cannot delete db record: {str(err)})")
                return error_response
        setOfArtifactIDs = set(tuple(sublist) for sublist in listOfArtifactIDs)
        error_response = jsonify({
                "status": 500,
                "status_code": 500,
                "message": "Request could not be submitted due to a server error, please try again after sometime.",
            })
        try:
            person = db.session.query(Person).filter(Person.id == login_session.user.person_id).first()
            cart_list = json.loads(person.cart)
            for item in cart_list[:]:
                if (item['artifact_group_id'], item['artifact_id']) in setOfArtifactIDs:
                    cart_list.remove(item)
            person.cart = json.dumps(cart_list)
            db.session.commit()
        except Exception as err:
            LOG.error(f"Cannot update cart: {str(err)})")
            return error_response

        response = jsonify({
            "status": 0,
            "message": "Request submitted successfully",
            "request": ArtifactRequestSchema().dump(request_entry),
            "newCart": person.cart
        })   

        response.headers.add('Access-Control-Allow-Origin', '*')
        response.status_code = 200
        return response