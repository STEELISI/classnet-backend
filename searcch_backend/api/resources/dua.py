
from searcch_backend.api.app import db, config_name
from searcch_backend.api.common.auth import verify_api_key
from flask import abort, jsonify, request
from flask_restful import reqparse, Resource
import sqlalchemy
from sqlalchemy import func, asc, desc, sql, and_, or_
import logging
from searcch_backend.models.model import *
from searcch_backend.models.schema import *
from bs4 import BeautifulSoup
import copy
import json
from datetime import datetime

LOG = logging.getLogger(__name__)

class DUAResource(Resource):

    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument(name='researchers',
                                   type=str,
                                   required=True,
                                   help='missing researchers') 
        self.reqparse.add_argument(name='project',
                                   type=str,
                                   required=True,
                                   help='missing project name')    
        self.reqparse.add_argument(name='project_description',
                                   type=str,
                                   required=True,
                                   help='missing project description') 
        self.reqparse.add_argument(name='dataset_name',
                                   type=str,
                                   required=True,
                                   help='missing dataset name')
        self.reqparse.add_argument(name='representative_researcher',
                                   type=str,
                                   required=True,
                                   help='missing representative_researcher') 
        self.reqparse.add_argument(name='frgpData',
                                   type=str,
                                   required=False,
                                   help='missing FRGP Data') 
                         
        super(DUAResource, self).__init__()

    def get(self, artifact_group_id):
        args = self.reqparse.parse_args()
        researchers = args['researchers']
        project = args['project']
        project_description = args['project_description']
        dataset_name = args['dataset_name']
        representative_researcher = args['representative_researcher']
        researchers = json.loads(researchers)
        representative_researcher = json.loads(representative_researcher)
        
        if  args['frgpData'] is not None:
            frgpData = json.loads(args['frgpData'])
        else:
            frgpData = {}
        
        dataset_category = db.session.query(Artifact.category).filter(artifact_group_id == Artifact.artifact_group_id).first()[0]
        dataset_category = "" if dataset_category is None else dataset_category  
        dataset_subcategory = db.session.query(Artifact.datasetSubCategory).filter(artifact_group_id == Artifact.artifact_group_id).first()[0]
        dataset_subcategory = "" if dataset_subcategory is None else dataset_subcategory  
        
        dua_name = db.session.query(DUA.dua_url).join(Artifact, and_(Artifact.provider == DUA.provider, Artifact.collection == DUA.collection)).filter(artifact_group_id == Artifact.artifact_group_id).first()[0]
        dua_file = open(f'searcch_backend/api/dua_content/{dua_name}', mode='r')
        dua_content = dua_file.read()
        dua_file.close()
        soup = BeautifulSoup(dua_content, 'html.parser')
        
        if dua_name == 'usc_dua.md':
            dua_a = soup.find(id='dua_a_to_replicate').parent
            dua_a_to_replicate_og = dua_a.find(id='dua_a_to_replicate')
            dua_a_to_replicate = copy.deepcopy(dua_a_to_replicate_og)
            dua_a_to_replicate_og.clear()
            for researcher in researchers:
                to_replicate = copy.deepcopy(dua_a_to_replicate)
                to_replicate.find(id='dua_a_name').string = researcher['name']
                to_replicate.find(id='dua_a_email').string = researcher['email']
                to_replicate.find(id='dua_a_contact').string = researcher['number']
                dua_a.append(to_replicate)
                        
            soup.find(id='dua_b_category').string = dataset_category
            soup.find(id='dua_b_sub_category').string = dataset_subcategory
            soup.find(id='dua_b_dataset_name').string = dataset_name

            soup.find(id='dua_c_project_name').string = project
            soup.find(id='dua_c_desc').string = project_description

            soup.find(id='rep_by').string = representative_researcher['name']
            soup.find(id='rep_email').string = representative_researcher['email']
            soup.find(id='rep_name').string = representative_researcher['name']
            soup.find(id='rep_title').string = representative_researcher['title']
            soup.find(id='rep_date').string = datetime.now().strftime("%m/%d/%Y")

            soup.find(id='poc_name').string = representative_researcher['name']
            soup.find(id='poc_email').string = representative_researcher['email']

        elif dua_name == 'merit_dua.md':
            soup.find(id='rep_org').string = representative_researcher['organization']
            soup.find(id='rep_name').string = representative_researcher['name']
            soup.find(id='rep_by').string = representative_researcher['name']
            soup.find(id='rep_title').string = representative_researcher['title']
            soup.find(id='rep_date').string = datetime.now().strftime("%m/%d/%Y")
        
        elif dua_name == 'frgp_dua_dload.md':
            dua_a = soup.find(id='dua_a_to_replicate').parent
            dua_a_to_replicate_og = dua_a.find(id='dua_a_to_replicate')
            dua_a_to_replicate = copy.deepcopy(dua_a_to_replicate_og)
            dua_a_to_replicate_og.clear()
            for researcher in researchers:
                to_replicate = copy.deepcopy(dua_a_to_replicate)
                to_replicate.find(id='dua_a_name').string = researcher['name']
                to_replicate.find(id='dua_a_email').string = researcher['email']
                to_replicate.find(id='dua_a_affiliation').string = researcher['organization']
                dua_a.append(to_replicate)
            soup.find(id="project_name").string = project
            soup.find(id='rep_name').string = representative_researcher['name']
            soup.find(id='rep_name_sig').string = representative_researcher['name']
            soup.find(id='rep_title').string = representative_researcher['title']
            soup.find(id='rep_email').string = representative_researcher['email']
            soup.find(id='rep_date').string = datetime.now().strftime("%m/%d/%Y")
            soup.find(id="supervisor_name").string = frgpData['supervisor_researcher']['name']
            soup.find(id="supervisor_title").string = frgpData['supervisor_researcher']['title']
            soup.find(id="supervisor_email").string = frgpData['supervisor_researcher']['email']
            soup.find(id="researcher_nationality").string = frgpData['nationality']
            soup.find(id="project_duration").string = frgpData['timeperiod']
            soup.find(id="data_storage").string = frgpData['storageLocation']
            soup.find(id="number_of_researchers").string = frgpData['numberOfResearchers']
            soup.find(id="grants").string = frgpData['grants']
            soup.find(id="data_usage").string = frgpData['dataUsage']
            soup.find(id="data_sharing").string = frgpData['resultSharing']
            soup.find(id="target_audience").string = frgpData['targetAudience']
            soup.find(id="data_disposal").string = frgpData['dataDisposal']
            soup.find(id="research_justification").string = project_description

        elif dua_name == 'dua-wes-20240420.md':
            dua_a = soup.find(id='dua_a_to_replicate').parent
            dua_a_to_replicate_og = dua_a.find(id='dua_a_to_replicate')
            dua_a_to_replicate = copy.deepcopy(dua_a_to_replicate_og)
            dua_a_to_replicate_og.clear()
            for researcher in researchers:
                to_replicate = copy.deepcopy(dua_a_to_replicate)
                to_replicate.find(id='dua_a_name').string = researcher['name']
                to_replicate.find(id='dua_a_email').string = researcher['email']
                to_replicate.find(id='dua_a_contact').string = researcher['number']
                dua_a.append(to_replicate)
                        
            soup.find(id='dua_b_category').string = dataset_category
            soup.find(id='dua_b_sub_category').string = dataset_subcategory
            soup.find(id='dua_b_dataset_name').string = dataset_name

            soup.find(id='dua_c_project_name').string = project
            soup.find(id='dua_c_desc').string = project_description

            soup.find(id='rep_by').string = representative_researcher['name']
            soup.find(id='rep_email').string = representative_researcher['email']
            soup.find(id='rep_name').string = representative_researcher['name']
            soup.find(id='rep_title').string = representative_researcher['title']
            soup.find(id='rep_date').string = datetime.now().strftime("%m/%d/%Y")

            soup.find(id='poc_name').string = representative_researcher['name']
            soup.find(id='poc_email').string = representative_researcher['email']

        elif dua_name == 'dua-LaSIC-Netflow-00.md':
            soup.find(id='rep_by').string = representative_researcher['name']
            soup.find(id='rep_org').string = representative_researcher['organization']
            soup.find(id='rep_name').string = representative_researcher['name']
            soup.find(id='rep_date').string = datetime.now().strftime("%m/%d/%Y")
            soup.find(id='rep_email').string = representative_researcher['email']
            soup.find(id='rep_ph').string = representative_researcher['number']
            soup.find(id='rep_name1').string = representative_researcher['name']
            soup.find(id='rep_email1').string = representative_researcher['email']
            soup.find(id='rep_ph1').string = representative_researcher['number']
            
        response = jsonify({"dua": str(soup)})
        response.status_code = 200
        return response
