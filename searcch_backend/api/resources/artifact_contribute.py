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
import re

LOG = logging.getLogger(__name__)


import re

def parse_description(description):

    key_value_dict = {}

    #Extracting Detailed Information part 
    match = re.search(r"Detailed Information\n\n(.*?)<\\pre>", description, re.DOTALL)

    # Extract the detailed information if available
    detailed_info = match.group(1) if match else "Detailed Information not found."

    # Wrap the information in a preformatted block for web display
    key_value_dict['datasetReadme'] =  f"<pre>{detailed_info}</pre>"

    # Remove <pre> and </pre> tags from the description
    description = description.replace('<pre>', '')
    description = description.replace('</pre>', '')

    # Regular expressions for matching old and new table formats
    regex_old = r'\+\-+\+.+?\+\-+\+'
    regex_new = r'┌\─+\┬\─+┐.+?└\─+┴\─+┘'

    using_old_format = False
    content_inside_table = None

    # Try to match the old format first
    matches = re.search(regex_old, description, re.S)
    if matches:
        content_inside_table = matches.group(0)
        using_old_format = True
    else:
        # If no match for the old format, try the new format
        matches = re.search(regex_new, description, re.S)
        if matches:
            content_inside_table = matches.group(0)

    if not content_inside_table:
        return description  # If no table is found, return the description unchanged

    # Remove borders depending on the format
    if using_old_format:
        # For old format, remove the `|-*+-*|` borders
        regex_old_2 = r'\|-*\+-*\|\n'
        content_inside_table_without_borders = re.sub(regex_old_2, '', content_inside_table)
    else:
        # For new format, remove the table borders
        regex_new_2 = r'┌\─+\┬\─+┐'
        regex_new_3 = r'└\─+┴\─+┘'
        regex_new_4 = r'├\─+\┼\─+\┤'
        content_inside_table_without_borders = re.sub(
            f"{regex_new_2}|{regex_new_3}|{regex_new_4}", '', content_inside_table
        )
    # Split lines and filter out empty lines
    lines = [line.strip() for line in content_inside_table_without_borders.split('\n') if line.strip()]

# Initialize a variable to track the previous key (in case of missing keys)
    previous_key = None

    # Iterate through each line in the lines list
    for line in lines:
        # Split the line by '│' (delimiter) and remove extra spaces
        delimeter = '|' if using_old_format else '│'
        elements = [element for element in line.split(delimeter)]

        if len(elements) == 4:
            # If there are at least two elements (key and value)
            key, value = elements[1].strip(), elements[2].strip()
            if key == '':
                # If the key is empty, append the value to the previous key's value
                if previous_key:
                    key_value_dict[previous_key] += ' ' + value
            else:
                # Otherwise, create a new key-value pair
                key_value_dict[key] = value
                previous_key = key
        else:
            LOG.error("!!!!MISSED DATA!!!!")

    return key_value_dict

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
        args["providerName"] = args["providerName"]

        try:
            user_email = db.session.query(Person.email).filter(Person.id == login_session.user.person_id).first()
            args["providerEmail"] = user_email[0]

            filtered_args = {k: v for k, v in args.items() if v != ''}
            LOG.error(f'Args submitted to antapi_datasets_meta_new: {filtered_args}')

            try:
                auth = AntAPIClientAuthenticator(**AUTH_DATASETS)
                response = antapi_datasets_meta_new(auth, **filtered_args, timeout=50)
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
        
        if(response.status_code == 200):
            try:
                contributed_artifact = ContributedArtifacts(user_id = login_session.user_id, title = args['datasetName'] )
                db.session.add(contributed_artifact)
                db.session.commit()
                LOG.error(f"Committed to table")

            except Exception as error:
                db.session.rollback()
                LOG.exception(f'Failed to write in the database. Error: {error}')

        return response
    
    def get(self):
        if has_api_key(request):
            verify_api_key(request)
        login_session = None
        if has_token(request):
            login_session = verify_token(request)
        if not (login_session):
            abort(400, description="insufficient permission to access Contribute Datasets page")
        artifact_id = request.args.get('artifactId')
        artifact_description = db.session.query(Artifact.description).filter(Artifact.id==artifact_id).first()
        if artifact_description:
            description = artifact_description[0]  # Extract the first element of the tuple (description)
            parsed_data = parse_description(description) 
        else:
            parsed_data = {}

        response = jsonify(parsed_data)
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.status_code = 200
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
        
        permissions_list = db.session.query(ProviderPermissions.provider, ProviderPermissions.collection).filter(ProviderPermissions.user_id == login_session.user_id).all()
        result= []

        if permissions_list is not None:
            result = [{"provider": permission.provider, "collection":permission.collection } for permission in permissions_list]     
        response = jsonify(result)
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.status_code = 200
        return response
        
class ArtifactLoad(Resource):
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument(name='artifactID',
                                   type=int,
                                   required=True,
                                   help='missing artifact ID')
        super().__init__()

    def get(self):
        if has_api_key(request):
            verify_api_key(request)
        login_session = None
        if has_token(request):
            login_session = verify_token(request)
        if not (login_session):
            abort(400, description="insufficient permission to access Contribute Datasets page")
        args = self.reqparse.parse_args()
        LOG.error()

