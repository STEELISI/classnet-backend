'''datasets: ingest dataset metadata'''

import re
from subprocess import (Popen, PIPE)
import logging
from datetime import datetime

from flask import (
    Blueprint,
    request,
    jsonify,
)

from ..tokens import validate_token
from ..flask_conf import (
    SECRET_KEY,
)


LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)

def _re_valid(pattern):
    compiled = re.compile(pattern)
    def _re_match(field_value):
        if not compiled.match(str(field_value)):
            return f"Value didn't match regex {pattern}"
        return ''
    return _re_match

def _dt_valid(field_value):
    try:
        datetime.fromisoformat(field_value)
    except ValueError:
        return f"Can't parse date-time {field_value}"
    return ''


# validators for metadata fields
# keys are fields, values tuples: (required, validator):
# where
#  required is (True/False), if False the field can be omited
#  validator(field_value) - either returns if valid or raises an exception if not
METADATA_FIELDS = {
    'datasetName':               (True,  _re_valid(r'^[A-Za-z0-9_\.\-]{5,250}$')),
    'shortDesc':                 (True,  _re_valid(r'^.{10,350}$')),
    'longDesc':                  (True,  _re_valid(r'^.{20,10000}$')),

#open-ended, for provider/host use
    'datasetClass':              (False, _re_valid(r'^.{0,30}$')),
    'commercialAllowed':         (False, _re_valid(r'^([Tt]rue|[Ff]alse)$')),
    'requestReviewRequired':     (False, _re_valid(r'^([Tt]rue|[Ff]alse)$')),
    'productReviewRequired':     (False, _re_valid(r'^([Tt]rue|[Ff]alse)$')),
    'availabilityStartDateTime': (True,  _dt_valid),
    'availabilityEndDateTime':   (True,  _dt_valid),
    'ongoingMeasurement':        (False, _re_valid(r'^([Tt]rue|[Ff]alse)$')),
    'collectionStartDateTime':   (True,  _dt_valid),
    'collectionEndDateTime':     (True,  _dt_valid),
    'byteSize':                  (True,  _re_valid(r'^\d{2,20}$')),
    'archivingAllowed':          (False, _re_valid(r'^([Tt]rue|[Ff]alse)$')),
    'keywordList':               (True,  _re_valid(r'^(([^ ,]{2,30}[, ])*[^ ,]{2,30}){0,20}$')),
    'formatList':                (True,  _re_valid(r'^(address-bitstring|adjacency-list|binary'
                                                   r'|coral|csv|dag|netflow-v5|netflow-v8'
                                                   r'|netflow-v9|pcap|snort|syslog|text|other)$')),
    'anonymizationList':         (True,  _re_valid(r'^(cryptopan-full|cryptopan/full'
                                                   r'|cryptopan/host|none|other)$')),
    'accessList':                (False, _re_valid(r'^(Google BigQuery|https|rsync|other)$')),
    'providerName':              (True,  _re_valid(r'^(MEMPHIS|MERIT|USC|COMUNDA:.*)$')),
    'uncompressedSize':          (False, _re_valid(r'^\d{2,20}$')),
    'expirationDays':            (False, _re_valid(r'^\d{1,3}$')),
    'groupingId':                (False, _re_valid(r'^[A-Za-z0-9_\.\- ]{5,250}$')),
    'useAgreement':              (True,  _re_valid(r'^(dua-ni-160816|frgp-continuous'
                                                   r'|merit-dua-v1|[a-z0-9\-\.]*)$')),
    'irbRequired':               (False, _re_valid(r'^([Tt]rue|[Ff]alse)$')),
    'retrievalInstructions':     (False, _re_valid(r'^(download|on-site)$')),
    # omit - currently unused or impact related:
    # checksumType checksumValue dataStructure publicAccessInstructions status
    # submissionMethod groupingSummaryFlag impactDoi datasetPath hostName
    # action metadataVersionDateTime
}


def _build_metadata(meta_json):
    for fld_name in meta_json.keys():
        if fld_name not in METADATA_FIELDS:
            LOG.warning("submitted field `%s` isn't supported, ignoring", fld_name)

    metadata = '{{:LANDER:Templates/LanderMetadata\n'
    for fld_name in METADATA_FIELDS:
        if fld_name in meta_json:
            if fld_name.endswith('DateTime'):
                # date time needs to be split into date and time fields
                fld_base = fld_name.removesuffix('DateTime')
                fld_datetime = datetime.fromisoformat(meta_json[fld_name])
                metadata += f'| {fld_base + 'Date'}={fld_datetime.strftime("%Y-%m-%d")}\n'
                metadata += f'| {fld_base + 'Time'}={fld_datetime.strftime("%H:%M:%S")}\n'
            else:
                metadata += f'| {fld_name}={meta_json[fld_name]}\n'
    metadata += '}}\n'
    return metadata


DATASETS = Blueprint('datasets', __name__)

@DATASETS.route('/datasets/meta/new', methods=['POST'])
@validate_token(secret_key=SECRET_KEY, realm='datasets')
def metadata_new(current_user):
    '''Create a new dataset metadata record'''
    LOG.info('Calling %s::metadata_new by %s', current_user.realm, current_user.email)

    dataset_json = request.json

    #check all fields are present and add missing defaults
    for (fld_name, (required, validator)) in METADATA_FIELDS.items():
        if fld_name in dataset_json:
            if validator is not None:
                err = validator(dataset_json[fld_name])

                if err != '':
                    msg = f"field `{fld_name}` didn't match expected pattern: {err}"
                    LOG.error(msg)
                    return jsonify({'message': msg}), 400
        else:
            if required:
                msg = f'Required metadata field `{fld_name}` is missing'
                LOG.error(msg)
                return jsonify({'message': msg}), 400

    # import metadata
    args = [ '/usr/bin/sudo', '-u', 'apachetrace',
             '/usr/local/bin/predict_wiki_edit.sh',
             f'LANDER:{dataset_json["datasetName"]}/landermeta' ]
    try:
        with Popen(args, stdout=PIPE, stderr=PIPE) as proc:
            err_out = proc.communicate(input=_build_metadata(dataset_json), timeout=10)[1]
        if proc.returncode != 0:
            msg = "can't create metadata in wiki: " + err_out
            LOG.error(msg)
            return jsonify({'message': msg}), 401
    except Exception as ex: # pylint: disable=broad-except
        msg = "can't create metadata in wiki: " + str(ex)
        LOG.error(msg)
        return jsonify({'message': msg}), 401

    # metadata created successfully
    return jsonify({'message': 'OK'}), 201


#@DATASETS.route('/datasets/meta/delete/<dataset_name>', methods=['POST'])
#@validate_token(secret_key=SECRET_KEY, realm='datasets')
#def metadata_delete(current_user, dataset_name):
#    '''Delete dataset metadata'''
#
#    LOG.info('Calling %s::metadata_delete by %s of %s',
#             current_user.realm, current_user.email, dataset_name)
