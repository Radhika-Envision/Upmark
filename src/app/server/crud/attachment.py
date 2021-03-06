import logging
import os
import hashlib
import tempfile

import botocore
from tornado.escape import json_encode
from tornado import gen
import tornado.web
from concurrent.futures import ThreadPoolExecutor

import aws
import base_handler
import errors
import model
from utils import ToSon


log = logging.getLogger('app.crud.attachment')

MAX_WORKERS = 4


class AttachmentHandler(base_handler.Paginate, base_handler.BaseHandler):

    @tornado.web.authenticated
    def get(self, attachment_id, file_name):
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            attachment = session.query(model.Attachment).get(attachment_id)

            if not attachment:
                raise errors.MissingDocError("No such attachment")

            policy = user_session.policy.derive({
                'org': attachment.organisation,
                'surveygroups': attachment.organisation.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('attachment_view')

            if attachment.storage == "aws":
                s3 = aws.session.client('s3', verify=False)
                object_loc = aws.S3_PATTERN.match(attachment.url)
                with tempfile.NamedTemporaryFile() as temp:
                    s3.download_file(
                        object_loc.group('bucket'),
                        object_loc.group('path'), temp.name)

                    with open(temp.name, "rb") as file:
                        blob = file.read()
            else:
                blob = attachment.blob

        self.set_header('Content-Type', 'application/octet-stream')
        self.set_header('Content-Disposition', 'attachment')
        self.write(bytes(blob))
        self.finish()

    @tornado.web.authenticated
    def delete(self, attachment_id, file_name):
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            attachment = session.query(model.Attachment).get(attachment_id)

            if attachment is None:
                raise errors.MissingDocError("No such attachment")

            policy = user_session.policy.derive({
                'org': attachment.organisation,
                'surveygroups': attachment.organisation.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('attachment_del')

            session.delete(attachment)

        self.finish()


class ResponseAttachmentsHandler(
        base_handler.Paginate, base_handler.BaseHandler):

    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    def put(self, submission_id, measure_id):
        son = self.request_son
        externals = son["externals"]
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            response = (
                session.query(model.Response)
                .get((submission_id, measure_id)))

            if response is None:
                raise errors.MissingDocError("No such response")

            org = response.submission.organisation
            policy = user_session.policy.derive({
                'org': org,
                'surveygroups': org.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('attachment_add')

            for external in externals:
                url = external.get('url', '').strip()
                file_name = external.get('file_name', '').strip()
                if url == '' and file_name == '':
                    continue
                if url == '':
                    raise errors.ModelError(
                        "URL required for link '%s'" % file_name)
                attachment = model.Attachment(
                    organisation=response.submission.organisation,
                    response=response,
                    url=url,
                    file_name=file_name,
                    storage='external'
                )

                session.add(attachment)
        self.get(submission_id, measure_id)

    @tornado.web.authenticated
    @gen.coroutine
    def post(self, submission_id, measure_id):
        fileinfo = self.request.files['file'][0]
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            response = (
                session.query(model.Response)
                .get((submission_id, measure_id)))

            if response is None:
                raise errors.MissingDocError("No such response")

            org = response.submission.organisation
            policy = user_session.policy.derive({
                'org': org,
                'surveygroups': org.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('attachment_add')

            if aws.session is not None:
                s3 = aws.session.resource('s3', verify=False)
                bucket = os.environ.get('AWS_BUCKET')
                hex_key = hashlib.sha256(bytes(fileinfo['body'])).hexdigest()
                s3_path = "{0}/{1}".format(
                    response.submission.organisation_id, hex_key)

                # Metadata can not contain non-ASCII characters - so encode
                # higher Unicode characters :/
                # https://github.com/boto/boto3/issues/478#issuecomment-180608544
                file_name_enc = (
                    fileinfo["filename"]
                    .encode('ascii', errors='backslashreplace')
                    .decode('ascii')
                    [:1024])

                try:
                    s3.Bucket(bucket).put_object(
                        Key=s3_path,
                        Metadata={'filename': file_name_enc},
                        Body=bytes(fileinfo['body']))
                except botocore.exceptions.ClientError as e:
                    raise errors.InternalModelError(
                        "Failed to write to data store", log_message=str(e))

            attachment = model.Attachment(
                organisation=response.submission.organisation,
                response=response,
                file_name=fileinfo["filename"]
            )

            if aws.session is not None:
                attachment.storage = "aws"
                aws_url = aws.s3_url.format(
                    region=aws.region_name,
                    bucket=bucket,
                    s3_path=s3_path)
                attachment.url = aws_url
            else:
                attachment.storage = "database"
                attachment.blob = bytes(fileinfo['body'])
            session.add(attachment)
            session.flush()

            attachment_id = str(attachment.id)

        self.set_header("Content-Type", "text/plain")
        self.write(attachment_id)
        self.finish()

    @tornado.web.authenticated
    def get(self, submission_id, measure_id):
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            response = (
                session.query(model.Response)
                .get((submission_id, measure_id)))

            if response is None:
                raise errors.MissingDocError("No such response")

            org = response.submission.organisation
            policy = user_session.policy.derive({
                'org': org,
                'surveygroups': org.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('attachment_view')

            query = (
                session.query(model.Attachment)
                .filter(model.Attachment.response == response))

            to_son = ToSon(
                r'/id$',
                r'/file_name$',
                r'/url$'
            )
            # Don't send internal URLs to client
            to_son_internal = ToSon(
                r'/id$',
                r'/file_name$'
            )

            sons = []
            for attachment in query.all():
                if not attachment.submeasure_id:
                    assert (attachment.organisation_id == org.id)
                    if attachment.storage == 'external':
                      sons.append(to_son(attachment))
                    else:
                         sons.append(to_son_internal(attachment))

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()


class ResponseSubmeasureAttachmentsHandler(
        base_handler.Paginate, base_handler.BaseHandler):

    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    def put(self, submission_id, measure_id, submeasure_id):
        son = self.request_son
        externals = son["externals"]
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            response = (
                session.query(model.Response)
                .get((submission_id, measure_id)))

            if response is None:
                raise errors.MissingDocError("No such response")

            org = response.submission.organisation
            policy = user_session.policy.derive({
                'org': org,
                'surveygroups': org.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('attachment_add')

            for external in externals:
                url = external.get('url', '').strip()
                file_name = external.get('file_name', '').strip()
                if url == '' and file_name == '':
                    continue
                if url == '':
                    raise errors.ModelError(
                        "URL required for link '%s'" % file_name)
                if measure_id!=submeasure_id:        
                    attachment = model.Attachment(
                        organisation=response.submission.organisation,
                        response=response,
                        url=url,
                        file_name=file_name,
                        submeasure_id=submeasure_id,
                        storage='external'
                    )
                else:
                    attachment = model.Attachment(
                        organisation=response.submission.organisation,
                        response=response,
                        url=url,
                        file_name=file_name,
                        storage='external'
                    )                        

                session.add(attachment)
        self.get(submission_id, measure_id, submeasure_id)

    @tornado.web.authenticated
    @gen.coroutine
    def post(self, submission_id, measure_id,submeasure_id):
        fileinfo = self.request.files['file'][0]
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            response = (
                session.query(model.Response)
                .get((submission_id, measure_id)))

            if response is None:
                raise errors.MissingDocError("No such response")

            org = response.submission.organisation
            policy = user_session.policy.derive({
                'org': org,
                'surveygroups': org.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('attachment_add')

            if aws.session is not None:
                s3 = aws.session.resource('s3', verify=False)
                bucket = os.environ.get('AWS_BUCKET')
                hex_key = hashlib.sha256(bytes(fileinfo['body'])).hexdigest()
                s3_path = "{0}/{1}".format(
                    response.submission.organisation_id, hex_key)

                # Metadata can not contain non-ASCII characters - so encode
                # higher Unicode characters :/
                # https://github.com/boto/boto3/issues/478#issuecomment-180608544
                file_name_enc = (
                    fileinfo["filename"]
                    .encode('ascii', errors='backslashreplace')
                    .decode('ascii')
                    [:1024])

                try:
                    s3.Bucket(bucket).put_object(
                        Key=s3_path,
                        Metadata={'filename': file_name_enc},
                        Body=bytes(fileinfo['body']))
                except botocore.exceptions.ClientError as e:
                    raise errors.InternalModelError(
                        "Failed to write to data store", log_message=str(e))



            if measure_id != submeasure_id:        
               attachment = model.Attachment(
                    organisation=response.submission.organisation,
                    response=response,
                    submeasure_id=submeasure_id,
                    file_name=fileinfo["filename"]
                )
            else:
                attachment = model.Attachment(
                    organisation=response.submission.organisation,
                    response=response,
                    file_name=fileinfo["filename"]
                )


            if aws.session is not None:
                attachment.storage = "aws"
                aws_url = aws.s3_url.format(
                    region=aws.region_name,
                    bucket=bucket,
                    s3_path=s3_path)
                attachment.url = aws_url
            else:
                attachment.storage = "database"
                attachment.blob = bytes(fileinfo['body'])
            session.add(attachment)
            session.flush()

            attachment_id = str(attachment.id)

        self.set_header("Content-Type", "text/plain")
        self.write(attachment_id)
        self.finish()

    @tornado.web.authenticated
    def get(self, submission_id, measure_id, submeasure_id):
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            response = (
                session.query(model.Response)
                .get((submission_id, measure_id)))

            if response is None:
                raise errors.MissingDocError("No such response")

            org = response.submission.organisation
            policy = user_session.policy.derive({
                'org': org,
                'surveygroups': org.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('attachment_view')

            query = (
                session.query(model.Attachment)
                .filter(model.Attachment.response == response))

            to_son = ToSon(
                r'/id$',
                r'/file_name$',
                r'/url$'
            )
            # Don't send internal URLs to client
            to_son_internal = ToSon(
                r'/id$',
                r'/file_name$'
            )

            sons = []
            for attachment in query.all():
                if  measure_id==submeasure_id or str(attachment.submeasure_id) == submeasure_id:
                    assert (attachment.organisation_id == org.id)
                    if attachment.storage == 'external':
                       sons.append(to_son(attachment))
                    else:
                       sons.append(to_son_internal(attachment))


        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()
