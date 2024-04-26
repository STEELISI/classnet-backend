# logic for /artifacts

from searcch_backend.api.app import db
from searcch_backend.models.model import *
from searcch_backend.models.schema import *
from searcch_backend.api.common.stats import StatsResource
from flask import abort, jsonify, request
from flask_restful import reqparse, Resource
from searcch_backend.api.common.auth import (verify_api_key, has_api_key, has_token, verify_token)
import logging
from antAPI.client.auth import AntAPIClientAuthenticator

from searcch_backend.api.ticket_creation.antapi_client_conf import AUTH_DATASETS
from datetime import datetime
from antAPI.client.datasets import antapi_datasets_meta_new

LOG = logging.getLogger(__name__)


class ArtifactContribute(Resource):
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument(name='datasetName',
                                   type=str,
                                   required=True,
                                   help='missing datasetName in query string')
        self.reqparse.add_argument(name='shortDesc',
                                   type=str,
                                   required=True,
                                   help='missing shortDesc in query string')
        self.reqparse.add_argument(name='longDesc',
                                   type=str,
                                   required=True,
                                   help='missing longDesc in query string')
        self.reqparse.add_argument(name='datasetClass',
                                   type=str,
                                   required=False,
                                   help='missing datasetClass in query string')
        self.reqparse.add_argument(name='commercialAllowed',
                                   type=str,
                                   required=False,
                                   help='missing commercialAllowed in query string')
        self.reqparse.add_argument(name='productReviewRequired',
                                   type=str,
                                   required=False,
                                   help='missing productReviewRequired in query string')
        self.reqparse.add_argument(name='availabilityStartDateTime',
                                   type=str,
                                   required=True,
                                   help='missing availabilityStartDateTime in query string')
        self.reqparse.add_argument(name='availabilityEndDateTime',
                                   type=str,
                                   required=True,
                                   help='missing availabilityEndDateTime in query string')
        self.reqparse.add_argument(name='ongoingMeasurement',
                                   type=str,
                                   required=False,
                                   help='missing ongoingMeasurement in query string')
        self.reqparse.add_argument(name='collectionStartDateTime',
                                   type=str,
                                   required=True,
                                   help='missing collectionStartDateTime in query string')
        self.reqparse.add_argument(name='collectionEndDateTime',
                                   type=str,
                                   required=True,
                                   help='missing collectionEndDateTime in query string')
        self.reqparse.add_argument(name='byteSize',
                                   type=str,
                                   required=True,
                                   help='missing byteSize in query string')
        self.reqparse.add_argument(name='archivingAllowed',
                                   type=str,
                                   required=False,
                                   help='missing archivingAllowed in query string')
        self.reqparse.add_argument(name='keywordList',
                                   type=str,
                                   required=True,
                                   help='missing keywordList in query string')
        self.reqparse.add_argument(name='formatList',
                                   type=str,
                                   required=True,
                                   help='missing formatList in query string')
        self.reqparse.add_argument(name='anonymizationList',
                                   type=str,
                                   required=True,
                                   help='missing anonymizationList in query string')
        self.reqparse.add_argument(name='accessList',
                                   type=str,
                                   required=False,
                                   help='missing accessList in query string')
        self.reqparse.add_argument(name='providerName',
                                   type=str,
                                   required=True,
                                   help='missing providerName in query string')
        self.reqparse.add_argument(name='uncompressedSize',
                                   type=str,
                                   required=False,
                                   help='missing uncompressedSize in query string')
        self.reqparse.add_argument(name='expirationDays',
                                   type=str,
                                   required=False,
                                   default=14,
                                   help='missing expirationDays in query string')
        self.reqparse.add_argument(name='groupingId',
                                   type=str,
                                   required=False,
                                   help='missing groupingId in query string')
        self.reqparse.add_argument(name='useAgreement',
                                   type=str,
                                   required=True,
                                   help='missing useAgreement in query string')
        self.reqparse.add_argument(name='irbRequired',
                                   type=str,
                                   required=False,
                                   help='missing irbRequired in query string')
        self.reqparse.add_argument(name='retrievalInstructions',
                                   type=str,
                                   required=False,
                                   help='missing retrievalInstructions in query string')
        self.reqparse.add_argument(name='datasetReadme',
                            type=str,
                            required=False,
                            help='missing datasetReadme in query string')

        super(ArtifactContribute, self).__init__()

    def post(self):
        # args = self.reqparse.parse_args()
        verify_api_key(request)
        login_session = verify_token(request)
        args = self.reqparse.parse_args()

        args["availabilityStartDateTime"] =datetime.strptime(args["availabilityStartDateTime"], "%Y-%m-%d")
        args["availabilityEndDateTime"] = datetime.strptime(args["availabilityEndDateTime"], "%Y-%m-%d")
        args["collectionStartDateTime"] =datetime.strptime(args["collectionStartDateTime"], "%Y-%m-%d")
        args["collectionEndDateTime"] =datetime.strptime(args["collectionEndDateTime"], "%Y-%m-%d")
        args["providerName"] = "COMUNDA:" + args["providerName"]
        try:
            user_email = db.session.query(Person.email).filter(Person.id == login_session.user.person_id).first()
            args["providerEmail"] = user_email[0]

            filtered_args = {k: v for k, v in args.items() if v != ''}
            LOG.error(f'Args submitted to antapi_datasets_meta_new: {filtered_args}')

            try:
                auth = AntAPIClientAuthenticator(**AUTH_DATASETS)
                response = antapi_datasets_meta_new(auth, **filtered_args)
                response = jsonify({
                    "message": "Dataset Contribution Successful!",
                    "success":"true"
                })
                response.headers.add('Access-Control-Allow-Origin', '*')
                response.status_code = 200

            except Exception as err: # pylint: disable=broad-except
                LOG.error(f"Failed to contribute dataset: {err}")
                response = jsonify({
                    "message": "Server error. Please try again later.",
                    "success":"false"
                })
                response.headers.add('Access-Control-Allow-Origin', '*')
                response.status_code = 201
        except Exception as err: # pylint: disable=broad-except
                LOG.error(f"Could not find user email.: {err}")
                response = jsonify({
                    "message": "Server error. Please try again later."
                })
                response.headers.add('Access-Control-Allow-Origin', '*')
                response.status_code = 201
        
        
        return response
    
class ProviderPermissionsList(Resource):
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        super().__init__()

    def get(self):
        if has_api_key(request):
            verify_api_key(request)
        login_session = None
        if has_token(request):
            login_session = verify_token(request)
        if not (login_session):
            abort(400, description="insufficient permission to access Contribute Datasets page")
        
        permissions_list = db.session.query(ProviderPermissions.provider).filter(ProviderPermissions.user_id == login_session.user_id).all()

        if permissions_list is None:
            permissions_list = []
        else:
            permissions_list = [provider[0] for provider in permissions_list]        
        response = jsonify({
                    "permissions_list": permissions_list
                })
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.status_code = 200
        return response
        
