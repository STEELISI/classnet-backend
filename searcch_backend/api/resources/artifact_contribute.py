# logic for /artifacts

from searcch_backend.api.app import db
from searcch_backend.models.model import *
from searcch_backend.models.schema import *
from searcch_backend.api.common.stats import StatsResource
from flask import jsonify, request
from flask_restful import reqparse, Resource
from searcch_backend.api.common.auth import (verify_api_key, has_api_key, has_token, verify_token)
import logging
from searcch_backend.api.ticket_creation.antAPI.client.auth import AntAPIClientAuthenticator

from searcch_backend.api.ticket_creation.antapi_client_conf import AUTH_DATASETS
# from searcch_backend.api.ticket_creation.antAPI.client.datasets import (
#    antapi_datasets_meta_new
# )
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
                                   type=bool,
                                   required=False,
                                   help='missing commercialAllowed in query string')
        self.reqparse.add_argument(name='productReviewRequired',
                                   type=bool,
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
                                   type=bool,
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
                                   type=bool,
                                   required=False,
                                   help='missing archivingAllowed in query string')
        self.reqparse.add_argument(name='keywordList',
                                   type=str,
                                   required=True,
                                   help='missing keywordList in query string')
        self.reqparse.add_argument(name='anonymizationList',
                                   type=str,
                                   required=True,
                                   help='missing keywordList in query string')
        self.reqparse.add_argument(name='accessList',
                                   type=str,
                                   required=False,
                                   help='missing accessList in query string')
        self.reqparse.add_argument(name='providerName',
                                   type=str,
                                   required=True,
                                   help='missing providerName in query string')
        self.reqparse.add_argument(name='uncompressedSize',
                                   type=int,
                                   required=False,
                                   help='missing uncompressedSize in query string')
        self.reqparse.add_argument(name='expirationDays',
                                   type=int,
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
                                   type=bool,
                                   required=False,
                                   help='missing irbRequired in query string')
        self.reqparse.add_argument(name='retrievalInstructions',
                                   type=str,
                                   required=False,
                                   help='missing retrievalInstructions in query string')

        super(ArtifactContribute, self).__init__()

    def post(self):
        # args = self.reqparse.parse_args()
        if has_api_key(request):
            verify_api_key(request)
        args = self.reqparse.parse_args()

        datasetName = args["datasetName"]
        shortDesc = args["shortDesc"]
        longDesc = args["longDesc"]
        datasetClass = args["datasetClass"]
        commercialAllowed = args["commercialAllowed"]
        productReviewRequired = args["productReviewRequired"]
        availabilityStartDateTime = args["availabilityStartDateTime"]
        availabilityEndDateTime = args["availabilityEndDateTime"]
        ongoingMeasurement = args["ongoingMeasurement"]
        collectionStartDateTime = args["collectionStartDateTime"]
        collectionEndDateTime = args["collectionEndDateTime"]
        byteSize = args["byteSize"]
        archivingAllowed = args["archivingAllowed"]
        keywordList = args["keywordList"]
        anonymizationList = args["anonymizationList"]
        accessList = args["accessList"]
        providerName = args["providerName"]
        uncompressedSize = args["uncompressedSize"]
        expirationDays = args["expirationDays"]
        groupingId = args["groupingId"]
        useAgreement = args["useAgreement"]
        irbRequired = args["irbRequired"]
        retrievalInstructions = args["retrievalInstructions"]
        LOG.error("HI from Contribute!")
        LOG.error("datasetName")

        metadata = {
                "datasetName": "xyz-Paul-test",
                "shortDesc": "short description",
                "longDesc": "long dataset description - this dataset contains network traffic collected...",
                "availabilityStartDateTime": datetime(2024, 1, 1, 0, 0, 0),
                "availabilityEndDateTime": datetime(2024, 1, 1, 0, 0, 1), 
                "collectionStartDateTime": datetime(2024, 1, 1, 0, 0, 0),
                "collectionEndDateTime": datetime(2024, 1, 1, 0, 0, 0),
                "byteSize": 100,
                "keywordList": "blah,blah blah",
                "formatList": "text",
                "anonymizationList": "cryptopan-full",
                "providerName": "COMUNDA:Paul",
                "useAgreement": "none"
         }
        try:
            auth = AntAPIClientAuthenticator(**AUTH_DATASETS)
            response = antapi_datasets_meta_new(auth, **metadata)
            LOG.error("antapi_datasets_meta_new response")

            LOG.error(response)

        except Exception as err: # pylint: disable=broad-except
            # undo the previous add
            LOG.error(f"Failed to contribute dataset: {err}")
            
    
        
        response = jsonify({
            "message": "Contribute endpoint Successful!!!!!"
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.status_code = 200
        return response