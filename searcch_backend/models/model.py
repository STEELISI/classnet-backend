from searcch_backend.api.app import db
from sqlalchemy.dialects.postgresql import TSVECTOR, BYTEA
from sqlalchemy import Table, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy import event
from sqlalchemy.sql import text
import hashlib

metadata = MetaData()
Base = declarative_base(metadata=metadata)


ARTIFACT_TYPES = (
    "publication", "presentation", "dag", "argus",
    "pcap", "netflow", "flowtools", "flowride", "fsdb", "csv", "custom"
)

ACCESS_TYPES = (
    "download", "onsite", "cloud"
)

ANON_TYPES = (
    "cryptopan-full", "cryptopan-host", "remove-host", "none", "custom"
)

ARTIFACT_IMPORT_TYPES = (
    "unknown", *ARTIFACT_TYPES
)
RELATION_TYPES = (
    "cites", "supplements", "extends", "uses", "describes",
    "requires", "processes", "produces"
)

class FileContent(db.Model):
    __tablename__ = "file_content"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    content = db.Column(db.LargeBinary(), nullable=False)
    hash = db.Column(db.LargeBinary(32), nullable=False)
    size = db.Column(db.BigInteger, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("hash"),
    )

    __user_ro_fields__ = (
        "hash",
    )

    @classmethod
    def make_hash(kls,content):
        m = hashlib.sha256()
        m.update(content)
        d = m.digest()
        return d

    def __repr__(self):
        return "<FileContent(id=%r,hash=%r,size=%r)>" % (
            self.id, self.hash, self.size )

#
# Both our primary key and hash are UNIQUE.  The migration that added this
# table IGNOREs conflicts on updates.  But that means that to make inserts of
# "new" content seamless, we have to update any objects without their primary
# keys set, if there is an existing hash match.  We also calculate the hash and
# size fields if they are missing.
#
@event.listens_for(FileContent, 'before_insert')
def file_content_fixups(mapper, connection, target):
    if not target.hash:
        target.hash = FileContent.make_hash(target.content)
    if target.size is None:
        target.size = len(target.content)
    if target.id is None:
        res = connection.execute(text("select id from file_content where hash=:hashval"),
                                 hashval=target.hash)
        row = res.first()
        if row:
            target.id = row["id"]


class ArtifactFile(db.Model):
    __tablename__ = "artifact_files"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    artifact_id = db.Column(db.Integer, db.ForeignKey("artifacts.id", ondelete='CASCADE'))
    url = db.Column(db.String(512), nullable=False)
    name = db.Column(db.String(512))
    filetype = db.Column(db.String(128), nullable=False)
    file_content_id = db.Column(db.Integer, db.ForeignKey("file_content.id", ondelete='CASCADE'))
    size = db.Column(db.BigInteger)
    mtime = db.Column(db.DateTime)
    
    file_content = db.relationship("FileContent", uselist=False)
    members = db.relationship("ArtifactFileMember", uselist=True)

    __table_args__ = (
        db.UniqueConstraint("artifact_id", "url"),)

    def __repr__(self):
        return "<ArtifactFile(id=%r,artifact_id=%r,file_content_id=%r,url=%r,name=%r,mtime=%r)>" % (
            self.id, self.artifact_id, self.file_content_id, self.url, self.name,
            self.mtime.isoformat() if self.mtime else "")


class ArtifactFileMember(db.Model):
    __tablename__ = "artifact_file_members"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    parent_file_id = db.Column(db.Integer, db.ForeignKey("artifact_files.id", ondelete='CASCADE'),nullable=False)
    pathname = db.Column(db.String(512), nullable=False)
    html_url = db.Column(db.String(512))
    download_url = db.Column(db.String(512))
    name = db.Column(db.String(512))
    filetype = db.Column(db.String(128), nullable=False)
    file_content_id = db.Column(db.Integer, db.ForeignKey("file_content.id", ondelete='CASCADE'))
    size = db.Column(db.Integer)
    mtime = db.Column(db.DateTime)

    file_content = db.relationship("FileContent",uselist=False)

    __table_args__ = (
        db.UniqueConstraint("parent_file_id", "pathname"),)

    def __repr__(self):
        return "<ArtifactFileMember(id=%r,parent_file_id=%r,pathname=%r,name=%r,html_url=%r,size=%r,mtime=%r)>" % (
            self.id,self.parent_file_id,self.pathname,self.name,self.html_url,self.size,
            self.mtime.isoformat() if self.mtime else "")


class ArtifactFunding(db.Model):
    __tablename__ = "artifact_funding"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    artifact_id = db.Column(db.Integer, db.ForeignKey(
        "artifacts.id", ondelete='CASCADE'), nullable=False)
    funding_org_id = db.Column(db.Integer, db.ForeignKey(
        "organizations.id", ondelete='CASCADE'), nullable=False)
    grant_number = db.Column(db.String(128), nullable=False)
    grant_url = db.Column(db.String(256), nullable=True)
    grant_title = db.Column(db.String(1024), nullable=True)

    __table_args__ = (
        db.UniqueConstraint("artifact_id", "funding_org_id", "grant_number"),)


class ArtifactMetadata(db.Model):
    __tablename__ = "artifact_metadata"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    artifact_id = db.Column(db.Integer, db.ForeignKey('artifacts.id', ondelete='CASCADE'))
    name = db.Column(db.String(64), nullable=False)
    value = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(256), nullable=True)
    source = db.Column(db.String(256), nullable=True)

    def __repr__(self):
        return "<ArtifactMetadata(artifact_id=%r,name=%r,value=%r,type=%r,source=%r)>" % (
            self.artifact_id, self.name, self.value, self.type,
            self.source)


class ArtifactPublication(db.Model):
    __tablename__ = "artifact_publications"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    artifact_id = db.Column(db.Integer, db.ForeignKey("artifacts.id", ondelete='CASCADE'))
    time = db.Column(db.DateTime, nullable=False)
    notes = db.Column(db.Text)
    publisher_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete='CASCADE'), nullable=False)
    version = db.Column(db.Integer, nullable=False)

    artifact = db.relationship("Artifact", uselist=False)
    publisher = db.relationship("User", uselist=False)

    def __repr__(self):
        return "<ArtifactPublication(id=%r,artifact_id=%r,time='%s',publisher='%r')>" % (
            self.id, self.artifact_id, self.time.isoformat(), self.publisher)


class Exporter(db.Model):
    __tablename__ = "exporters"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), nullable=False)
    version = db.Column(db.String(32))

    __table_args__ = (
        db.UniqueConstraint("name", "version"),)

    def __repr__(self):
        return "<Exporter(id=%r,name='%s',version='%s')>" % (self.id, self.name, self.version)


class ArtifactTag(db.Model):
    __tablename__ = "artifact_tags"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    artifact_id = db.Column(db.Integer, db.ForeignKey('artifacts.id', ondelete='CASCADE'))
    tag = db.Column(db.String(256), nullable=False)
    source = db.Column(db.String(256), nullable=False, default="")

    __table_args__ = (
        db.UniqueConstraint("tag", "artifact_id", "source"),)

    def __repr__(self):
        return "<ArtifactTag(artifact_id=%r,tag=%r,source=%r)>" % (
            self.artifact_id, self.tag, self.source)


class ArtifactCuration(db.Model):
    __tablename__ = "artifact_curations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    artifact_id = db.Column(db.Integer, db.ForeignKey("artifacts.id", ondelete='CASCADE'))
    time = db.Column(db.DateTime, nullable=False)
    notes = db.Column(db.Text)
    opdata = db.Column(db.Text,nullable=False)
    curator_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete='CASCADE'), nullable=False)

    curator = db.relationship("User")

    def __repr__(self):
        return "<ArtifactCuration(id=%r,artifact_id=%r,time='%s',curator='%r')>" % (
            self.id, self.artifact_id, self.time.isoformat(),
            self.curator)


class ArtifactAffiliation(db.Model):
    __tablename__ = "artifact_affiliations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    artifact_id = db.Column(db.Integer, db.ForeignKey(
        "artifacts.id", ondelete='CASCADE'), nullable=False)
    affiliation_id = db.Column(db.Integer, db.ForeignKey(
        "affiliations.id", ondelete='CASCADE'), nullable=False)
    roles = db.Column(
        db.Enum("Author", "ContactPerson", "Other",
                name="artifact_affiliation_enum"),
        nullable=False, default="Author")

    affiliation = db.relationship("Affiliation", uselist=False)

    __table_args__ = (
        db.UniqueConstraint("artifact_id", "affiliation_id", "roles"),)

    def __repr__(self):
        return "<ArtifactAffiliation(artifact_id=%r,affiliation_id=%r,roles=%r)>" % (
            self.artifact_id, self.affiliation_id, self.roles)


class ArtifactRelationship(db.Model):
    # The ArtifactRelationship class declares a db.relationship between two SEARCCH artifacts.

    __tablename__ = "artifact_relationships"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    artifact_id = db.Column(db.Integer, db.ForeignKey("artifacts.id", ondelete='CASCADE'))
    artifact_group_id = db.Column(db.Integer, db.ForeignKey("artifact_groups.id", ondelete='CASCADE'), nullable=False)
    relation = db.Column(db.Enum(
        *RELATION_TYPES,
        name="artifact_relationship_enum"))
    related_artifact_id = db.Column(db.Integer, db.ForeignKey("artifacts.id", ondelete='CASCADE'))
    related_artifact_group_id = db.Column(db.Integer, db.ForeignKey("artifact_groups.id", ondelete='CASCADE'), nullable=False)

    related_artifact_group = db.relationship(
        "ArtifactGroup", uselist=False, foreign_keys=[related_artifact_group_id], viewonly=True)

    __table_args__ = (
        db.UniqueConstraint("artifact_group_id", "relation", "related_artifact_group_id"),)

    __user_ro_relationships__ = (
        "related_artifact_group",
    )


class ArtifactRelease(db.Model):
    __tablename__ = "artifact_releases"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    artifact_id = db.Column(db.Integer, db.ForeignKey("artifacts.id", ondelete='CASCADE'))
    url = db.Column(db.String(512))
    author_login = db.Column(db.String(128))
    author_email = db.Column(db.String(128))
    author_name = db.Column(db.String(128))
    tag = db.Column(db.String(128))
    title = db.Column(db.String(1024))
    time = db.Column(db.DateTime)
    notes = db.Column(db.Text)

    def __repr__(self):
        return "<ArtifactRelease(id=%r,artifact_id=%r,url='%s',title='%s',author_email='%s',time='%s')>" % (
            self.id, self.artifact_id, self.url, self.title, self.author_email,
            self.time.isoformat() if self.time else "")


class Importer(db.Model):
    __tablename__ = "importers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), nullable=False)
    version = db.Column(db.String(32))

    __table_args__ = (
        db.UniqueConstraint("name", "version"),)

    def __repr__(self):
        return "<Importer(id=%r,name='%s',version='%s')>" % (self.id, self.name, self.version)


class Person(db.Model):
    __tablename__ = "persons"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(1024), nullable=True)
    email = db.Column(db.String(256), nullable=True)
    emailAuthenticated = db.Column(db.Boolean, nullable=True, default=False)
    countryCode = db.Column(db.String(16), nullable = True)
    mobileNumber = db.Column(db.String(16), nullable = True)

    login_id = db.Column(db.String(256), nullable=True)
    profile_photo = db.Column(BYTEA, nullable=True)
    research_interests = db.Column(db.Text, nullable=True)
    website = db.Column(db.Text, nullable=True)
    person_tsv = db.Column(TSVECTOR)
    position = db.Column(db.Text, nullable=True)
    public_key = db.Column(db.Text, nullable=True)
    cart = db.Column(db.Text, nullable=True )

    def __repr__(self):
        return "<Person(id=%r,name=%r, email=%r)>" % (
            self.id, self.name, self.email)


class UserAuthorization(db.Model):
    __tablename__ = "user_authorizations"

    user_id = db.Column(db.Integer, db.ForeignKey(
        "users.id", ondelete='CASCADE'), primary_key=True)
    roles = db.Column(
        db.Enum("Uploader", "Editor", "Curator",
                name="user_authorization_role_enum"),
        nullable=False)
    scope = db.Column(
        db.Enum("Org", "Artifact",
                name="user_authorization_scope_enum"),
        nullable=False)
    # A NULL scoped_id is a wildcard, meaning everything.
    scoped_id = db.Column(db.Integer, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("user_id", "roles", "scope", "scoped_id"),)

    def __repr__(self):
        return "<UserAuthorization(user_id=%r,roles='%s',scope='%s',scoped_id='%s')>" % (
            self.user_id, self.roles, self.scope, str(self.scoped_id))


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    person_id = db.Column(db.Integer, db.ForeignKey(
        "persons.id", ondelete='CASCADE'), nullable=False)
    person = db.relationship("Person", uselist=False)
    can_admin = db.Column(db.Boolean, nullable=False, default=False)

    __table_args__ = (
        db.UniqueConstraint("person_id"),)

    def __repr__(self):
        return "<User(id=%r,person_id=%r,can_admin=%r)>" % (
            self.id, self.person_id, self.can_admin)


class License(db.Model):
    __tablename__ = "licenses"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    short_name = db.Column(db.String(64))
    long_name = db.Column(db.String(512), nullable=False)
    url = db.Column(db.String(1024), nullable=False)
    verified = db.Column(db.Boolean, nullable=False, default=False)

    __table_args__ = (
        db.UniqueConstraint("long_name", "url", "verified"),)

    __object_from_json_allow_pk__ = True

    def __repr__(self):
        return "<License(id=%r,long_name=%r,short_name=%r,url=%r,verified=%r)>" % (
            self.id, self.long_name, self.short_name, self.url, self.verified)


class Organization(db.Model):
    __tablename__ = "organizations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(1024), nullable=False)
    type = db.Column(
        db.Enum("Institution", "Company", "Institute", "ResearchGroup", "Sponsor", "Other",
                name="organization_enum"),
        nullable=False)
    url = db.Column(db.String(512), nullable=True)
    state = db.Column(db.String(64), nullable=True)
    country = db.Column(db.String(64), nullable=True)
    latitude = db.Column(db.Float(), nullable=True)
    longitude = db.Column(db.Float(), nullable=True)
    address = db.Column(db.String(512), nullable=True)
    verified = db.Column(db.Boolean, nullable=False, default=False)
    org_tsv = db.Column(TSVECTOR)

    def __repr__(self):
        return "<Organization(name=%r,type=%r,url=%r,verified=%r)>" % (
            self.name, self.type, self.url, self.verified)


class Affiliation(db.Model):
    __tablename__ = "affiliations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    person_id = db.Column(db.Integer, db.ForeignKey(
        "persons.id", ondelete='CASCADE'), nullable=False)
    org_id = db.Column(db.Integer, db.ForeignKey(
        "organizations.id", ondelete='CASCADE'))

    person = db.relationship("Person", uselist=False)
    org = db.relationship("Organization", uselist=False)

    __table_args__ = (
        db.UniqueConstraint("person_id", "org_id"),)

    def __repr__(self):
        return "<Affiliation(person=%r,org=%r)>" % (
            self.person, self.org)


class UserAffiliation(db.Model):
    __tablename__ = "user_affiliations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey(
        "users.id", ondelete='CASCADE'), nullable=False)
    org_id = db.Column(db.Integer, db.ForeignKey(
        "organizations.id", ondelete='CASCADE'))

    user = db.relationship("User", uselist=False)
    org = db.relationship("Organization", uselist=False)

    __table_args__ = (
        db.UniqueConstraint("user_id", "org_id"),)

    def __repr__(self):
        return "<UserAffiliation(user=%r,org=%r)>" % (
            self.user, self.org)


class PersonMetadata(db.Model):
    __tablename__ = "person_metadata"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    person_id = db.Column(db.Integer, db.ForeignKey(
        "persons.id", ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(64), nullable=False)
    value = db.Column(db.String(1024), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("person_id", "name"),)

    def __repr__(self):
        return "<PersonMetadata(person_id=%r,name='%s')>" % (
            self.id, self.name)


class Badge(db.Model):
    __tablename__ = "badges"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(1024), nullable=False)
    url = db.Column(db.String(1024), nullable=False)
    image_url = db.Column(db.String(1024))
    description = db.Column(db.Text)
    version = db.Column(db.String(256), nullable=False, default="")
    organization = db.Column(db.String(1024), nullable=False)
    venue = db.Column(db.String(1024))
    issue_time = db.Column(db.DateTime)
    doi = db.Column(db.String(128))
    verified = db.Column(db.Boolean, nullable=False, default=False)

    __table_args__ = (
        db.UniqueConstraint("title", "url", "version", "organization"),)

    __object_from_json_allow_pk__ = True

    def __repr__(self):
        return "<Badge(title=%r,url=%r,version=%r,organization=%r,venue=%r,verified=%r)>" % (
            self.title, self.url, self.version, self.organization, self.venue, self.verified)


class DUA(db.Model):
    __tablename__ = "dua"

    collection = db.Column(db.String(1024), nullable=False, primary_key=True)
    provider = db.Column(db.String(1024), nullable=False, primary_key=True)
    dua_url = db.Column(db.Text(), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("collection", "provider"),)

    def __repr__(self):
        return "<DUA(collection=%r,provider=%r, dua_url=%r)>" % (
            self.collection, self.provider, self.dua_url)


class ArtifactBadge(db.Model):
    __tablename__ = "artifact_badges"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    artifact_id = db.Column(db.Integer, db.ForeignKey(
        "artifacts.id", ondelete='CASCADE'), nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey(
        "badges.id", ondelete='CASCADE'), nullable=False)

    badge = db.relationship("Badge", uselist=False)

    __table_args__ = (
        db.UniqueConstraint("artifact_id", "badge_id"),)

    def __repr__(self):
        return "<ArtifactBadge(artifact_id=%r,badge_id=%r)>" % (
            self.artifact_id, self.badge_id)


class ArtifactRatings(db.Model):
    __tablename__ = "artifact_ratings"
    __table_args__ = (
        db.CheckConstraint(
            'rating >= 0', name='artifact_ratings_valid_rating_lower_bound'),
        db.CheckConstraint(
            'rating <= 5', name='artifact_ratings_valid_rating_upper_bound'),
        db.UniqueConstraint("artifact_group_id", "user_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete='CASCADE'), nullable=False)
    artifact_id = db.Column(db.Integer, db.ForeignKey(
        "artifacts.id", ondelete='CASCADE'), nullable=True)
    artifact_group_id = db.Column(db.Integer, db.ForeignKey(
        "artifact_groups.id", ondelete='CASCADE'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return "<ArtifactRatings(id=%r, user_id=%r,artifact_group_id=%r,rating='%d')>" % (
            self.id, self.user_id, self.artifact_group_id, self.rating)


class ArtifactReviews(db.Model):
    __tablename__ = "artifact_reviews"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete='CASCADE'), nullable=False)
    artifact_id = db.Column(db.Integer, db.ForeignKey(
        "artifacts.id", ondelete='CASCADE'), nullable=True)
    artifact_group_id = db.Column(db.Integer, db.ForeignKey(
        "artifact_groups.id", ondelete='CASCADE'), nullable=False)
    review = db.Column(db.Text, nullable=False)
    review_time = db.Column(db.DateTime, nullable=False)

    reviewer = db.relationship("User")

    def __repr__(self):
        return "<ArtifactReviews(id=%r, user_id=%r,artifact_group_id=%r,review='%s')>" % (
            self.id, self.user_id, self.artifact_group_id, self.review)


class ArtifactFavorites(db.Model):
    __tablename__ = "artifact_favorites"
    __table_args__ = (
        db.UniqueConstraint("artifact_group_id", "user_id"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete='CASCADE'), nullable=False)
    artifact_id = db.Column(db.Integer, db.ForeignKey(
        "artifacts.id", ondelete='CASCADE'), nullable=True)
    artifact_group_id = db.Column(db.Integer, db.ForeignKey(
        "artifact_groups.id", ondelete='CASCADE'), nullable=False)

    def __repr__(self):
        return "<ArtifactFavorites(id=%r, user_id=%r,artifact_group_id=%r)>" % (
            self.id, self.user_id, self.artifact_group_id)


class Sessions(db.Model):
    __tablename__ = "sessions"
    __table_args__ = (
        db.UniqueConstraint("sso_token",),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete='CASCADE'), nullable=False)
    sso_token = db.Column(db.String(64), nullable=False)
    expires_on = db.Column(db.DateTime, nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    user = db.relationship("User", uselist=False)
    otp = db.Column(db.Integer, nullable=True)

    def __repr__(self):
        return "<Session(id=%r, user_id=%r, user_can_admin=%r, sso_token=%r, is_admin=%r)>" \
            % (self.id, self.user_id, self.user.can_admin, self.sso_token, self.is_admin)


class ArtifactGroup(db.Model):
    __tablename__ = "artifact_groups"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete='CASCADE'), nullable=False)
    publication_id = db.Column(db.Integer, db.ForeignKey("artifact_publications.id", ondelete='CASCADE'), nullable=True)
    next_version = db.Column(db.Integer, nullable=False)

    owner = db.relationship("User", uselist=False)
    publication = db.relationship("ArtifactPublication", uselist=False)
    relationships = db.relationship(
        "ArtifactRelationship",uselist=True,
        foreign_keys=[ArtifactRelationship.artifact_group_id])
    reverse_relationships = db.relationship(
        "ArtifactRelationship",uselist=True,
        foreign_keys=[ArtifactRelationship.related_artifact_group_id])
    publications = db.relationship(
        "ArtifactPublication", uselist=True, viewonly=True,
        secondary="join(Artifact, ArtifactPublication, Artifact.id == ArtifactPublication.artifact_id)",
        secondaryjoin="Artifact.id == ArtifactPublication.artifact_id",
        primaryjoin="ArtifactGroup.id == Artifact.artifact_group_id")

    #secondary="join(Artifact, ArtifactGroup, Artifact.artifact_group_id == ArtifactGroup.id)",
    #secondaryjoin="Artifact.artifact_group_id == ArtifactGroup.id",
    __user_ro_fields__ = (
        "owner_id",
    )
    __user_ro_relationships__ = (
        "owner", "relationships", "reverse_relationships"
    )

    def __repr__(self):
        return "<ArtifactGroup(id=%r, owner=%r)>" \
            % (self.id, self.owner_id)


class Artifact(db.Model):
    # The Artifact class provides an internal model of a SEARCCH artifact.
    # An artifact is an entity that may be added to or edited within the SEARCCH Hub.

    __tablename__ = "artifacts"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    artifact_group_id = db.Column(
        db.Integer, db.ForeignKey("artifact_groups.id", ondelete='CASCADE'), nullable=False)
    type = db.Column(db.Enum(*ARTIFACT_TYPES,name="artifact_enum"))
    url = db.Column(db.String(1024), nullable=False)
    ext_id = db.Column(db.String(512))
    title = db.Column(db.Text, nullable=False)
    name = db.Column(db.String(1024), nullable=True)
    ctime = db.Column(db.DateTime, nullable=False)
    mtime = db.Column(db.DateTime, nullable=True)
    description = db.Column(db.Text, nullable=True)
    license_id = db.Column(db.Integer, db.ForeignKey(
        "licenses.id", ondelete='CASCADE'), nullable=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete='CASCADE'), nullable=True)
    importer_id = db.Column(db.Integer, db.ForeignKey(
        "importers.id", ondelete='CASCADE'), nullable=True)
    exporter_id = db.Column(db.Integer, db.ForeignKey(
        "exporters.id", ondelete='CASCADE'), nullable=True)
    parent_id = db.Column(db.Integer, db.ForeignKey(
        "artifacts.id", ondelete='CASCADE'), nullable=True)

    artifact_group = db.relationship("ArtifactGroup", uselist=False)
    exporter = db.relationship("Exporter", uselist=False)
    # Needs to map to ArtifactLicense(id,license_id)
    license = db.relationship("License", uselist=False)
    meta = db.relationship("ArtifactMetadata")
    tags = db.relationship("ArtifactTag")
    labels = db.relationship("Labels")
    files = db.relationship("ArtifactFile")
    # This is "root" -- we need a permissions/role table?
    owner = db.relationship("User", uselist=False)
    # Per-version; only null when user manually created this version
    importer = db.relationship("Importer", uselist=False)
    curations = db.relationship("ArtifactCuration")
    publication = db.relationship("ArtifactPublication", uselist=False)
    releases = db.relationship("ArtifactRelease", uselist=True)
    affiliations = db.relationship("ArtifactAffiliation")
    badges = db.relationship("ArtifactBadge", uselist=True)
    fromtime = db.Column(db.DateTime)
    totime = db.Column(db.DateTime)
    size = db.Column(db.BigInteger)
    access = db.Column(db.Enum(*ACCESS_TYPES,name="access_enum"))
    anonymization = db.Column(db.Enum(*ANON_TYPES,name="anon_enum"))
    collection = db.Column(db.String(1024), nullable=False)
    provider = db.Column(db.String(1024), nullable=False)
    shortdesc = db.Column(db.String(1024), nullable=False)
    irb = db.Column(db.Boolean,  nullable=False, default=False)
    groupingId = db.Column(db.String(512), nullable = True)
    
    category = db.Column(db.Text, nullable=True)
    datasetSubCategory = db.Column(db.Text, nullable=True)

    
    # NB: all foreign keys are read-only, so not included here.
    __user_ro_fields__ = (
        "artifact_group_id","parent_id","version","ctime","mtime","ext_id","owner_id" )
    __user_ro_relationships__ = (
        "exporter","owner","importer","curations","publication","artifact_group"
    )
    __user_skip_relationships__ = (
        "curations",
    )
    __clone_skip_relationships__ = (
        'curations', 'publication', 'owner', 'importer', 'exporter',
    )
    __clone_skip_fields__ = (
        'importer_id', 'exporter_id', 'parent_id', 'owner_id', 'ctime', 'mtime',
    )
    __table_args__ = (
        db.UniqueConstraint("artifact_group_id"),
    )


    def __repr__(self):
        return "<Artifact(id=%r,title='%s',description='%s',type='%s',url='%s',owner='%r',files='%r',tags='%r',metadata='%r',publication='%r')>" % (
            self.id, self.title, self.description, self.type, self.url, self.owner, self.files, self.tags, self.meta, self.publication)


class ArtifactSearchMaterializedView(db.Model):
    # The ArtifactSearchMaterializedView class provides an internal model of a SEARCCH artifact's searchable index.
    __tablename__ = "artifact_search_view"
    dummy_id = db.Column(db.Integer, primary_key=True)  # this id does not actually exist in the database
    artifact_group_id = db.Column(db.Integer, db.ForeignKey("artifact_groups.id", ondelete='CASCADE'), nullable=False)
    artifact_id = db.Column(db.Integer)
    doc_vector = db.Column(TSVECTOR)
    
    def __repr__(self):
        return "<ArtifactSearchMaterializedView(artifact_id=%r,doc_vector='%s')>" % (self.id, self.doc_vector)


ARTIFACT_IMPORT_STATUSES = (
    "pending", "scheduled", "running", "completed", "failed"
)
ARTIFACT_IMPORT_PHASES = (
    "start", "validate", "import", "retrieve", "extract", "done"
)

class ArtifactImport(db.Model):
    """
    ArtifactImport represents an ongoing or completed artifact import session.
    """

    __tablename__ = "artifact_imports"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    type = db.Column(db.Enum(
        *ARTIFACT_IMPORT_TYPES,name="artifact_imports_type_enum"),
        nullable=False)
    url = db.Column(db.String(1024), nullable=False)
    importer_module_name = db.Column(db.String(256), nullable=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete='CASCADE'), nullable=False)
    ctime = db.Column(db.DateTime, nullable=False)
    mtime = db.Column(db.DateTime, nullable=True)
    # Status of the import from back end's perspective
    status = db.Column(db.Enum(
        *ARTIFACT_IMPORT_STATUSES,
        name="artifact_imports_status_enum"), nullable=False)
    # Importer phase
    phase = db.Column(db.Enum(
        *ARTIFACT_IMPORT_PHASES,
        name="artifact_imports_phase_enum"), nullable=False)
    message = db.Column(db.Text, nullable=True)
    progress = db.Column(db.Float, default=0.0)
    bytes_retrieved = db.Column(db.Integer, default=0, nullable=False)
    bytes_extracted = db.Column(db.Integer, default=0, nullable=False)
    log = db.Column(db.Text, nullable=True)
    #
    # If we are reimporting to create a new version, we can immediately set
    # artifact_group_id and parent_artifact_id.  Otherwise we wait to create a
    # new artifact_group_id and artifact_id until the import succeeds (once
    # status=complete and phase=done).
    #
    artifact_group_id = db.Column(db.Integer, db.ForeignKey("artifact_groups.id", ondelete='CASCADE'), nullable=True)
    parent_artifact_id = db.Column(db.Integer, db.ForeignKey("artifacts.id", ondelete='CASCADE'), nullable=True)
    artifact_id = db.Column(db.Integer, db.ForeignKey("artifacts.id", ondelete='CASCADE'), nullable=True)
    archived = db.Column(db.Boolean, nullable=False, default=False)

    owner = db.relationship("User", uselist=False)
    artifact_group = db.relationship("ArtifactGroup", uselist=False)
    artifact = db.relationship("Artifact", uselist=False,
        foreign_keys=[artifact_id])

    __table_args__ = (
        db.UniqueConstraint("owner_id","url","artifact_group_id","artifact_id"),
    )

    def __repr__(self):
        return "<ArtifactImport(id=%r,type=%r,url=%r,importer_module_name=%r,owner=%r,status=%r,artifact_group=%r,artifact=%r)>" % (
            self.id, self.type, self.url, self.importer_module_name,
            self.owner, self.status, self.artifact_group, self.artifact)

ARTIFACT_OWNER_REQUEST_STATUS = (
    "pending", "approved", "rejected", "pre_approved"
)

class ArtifactOwnerRequest(db.Model):
    # The ArtifactOwnerRequest class stores all the artifact owership requesst

    __tablename__ = "artifact_owner_request"
    __table_args__ = (
        db.UniqueConstraint("artifact_group_id", "user_id"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete='CASCADE'), nullable=False)
    artifact_group_id = db.Column(db.Integer, db.ForeignKey("artifact_groups.id", ondelete='CASCADE'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    ctime = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.Enum(*ARTIFACT_OWNER_REQUEST_STATUS,name="artifact_owner_request_status_enum"), nullable=False)
    action_message = db.Column(db.Text, nullable=True)
    action_time = db.Column(db.DateTime, nullable=True)
    action_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete='CASCADE'), nullable=True)

    user = db.relationship("User", uselist=False, foreign_keys=[user_id])
    action_by_user = db.relationship("User", uselist=False, foreign_keys=[action_by_user_id])

class ImporterInstance(db.Model):
    """
    Represents registered, authorized importer instances.
    """
    __tablename__ = "importer_instances"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    url = db.Column(db.String(1024), nullable=False)
    key = db.Column(db.String(128), nullable=False)
    max_tasks = db.Column(db.Integer, nullable=False)
    status = db.Column(db.Enum(
        "up", "down", "stale", name="importer_instances_status_enum"),
        nullable=False)
    status_time = db.Column(db.DateTime, nullable=False)
    admin_status = db.Column(db.Enum(
        "enabled","disabled", name="importer_instances_admin_status_enum"),
        nullable=False)
    admin_status_time = db.Column(db.DateTime, nullable=False)

    scheduled = db.relationship("ImporterSchedule", uselist=True)

    __table_args__ = (
        db.UniqueConstraint("url","key"),
    )

    def __repr__(self):
        return "<ImporterInstance(id=%r,url=%r,status=%r,status_time=%r,admin_status=%r,admin_status_time=%r)>" % (
            self.id, self.url, self.status, self.status_time, self.admin_status, self.admin_status_time)


class ImporterSchedule(db.Model):
    """
    Represents scheduled and pending imports.
    """
    __tablename__ = "importer_schedules"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    artifact_import_id = db.Column(
        db.Integer, db.ForeignKey("artifact_imports.id", ondelete='CASCADE'), nullable=False)
    importer_instance_id = db.Column(
        db.Integer, db.ForeignKey("importer_instances.id", ondelete='CASCADE'), nullable=True)
    schedule_time = db.Column(db.DateTime, nullable=True)
    # NB: this is the ID of the artifact import in the importer instance
    remote_id = db.Column(db.Integer, nullable=True)
    
    artifact_import = db.relationship("ArtifactImport", uselist=False)
    importer_instance = db.relationship("ImporterInstance", uselist=False)

    __table_args__ = (
        db.UniqueConstraint("artifact_import_id"),
    )

    def __repr__(self):
        return "<ImporterSchedule(id=%r,artifact_import=%r,importer_instance=%r,schedule_time=%r" % (
            self.id, self.artifact_import, self.importer_instance, self.schedule_time)


# Models to capture Statistical Data

class StatsArtifactViews(db.Model):
    __tablename__ = "stats_views"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    artifact_group_id = db.Column(db.Integer, db.ForeignKey("artifact_groups.id", ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete='CASCADE'), nullable=True)
    view_count = db.Column(db.Integer, nullable=False)
    def __repr__(self):
        return "<StatsArtifactViews(id=%r, artifact_group_id=%r, user_id=%r,view_count=%r)>" % (self.id, self.artifact_group_id, self.user_id, self.view_count)

class StatsSearches(db.Model):
    __tablename__ = "stats_searches"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    search_term = db.Column(db.String(512), nullable=False)
    def __repr__(self):
        return "<StatsSearches(id=%r, search_term=%r)>" % (self.id, self.search_term)

class StatsRecentViews(db.Model):
    __tablename__ = "recent_views"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.Integer, nullable=False)
    artifact_group_id = db.Column(db.Integer, db.ForeignKey("artifact_groups.id", ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete='CASCADE'), nullable=True)
    view_count = db.Column(db.Integer, nullable=False)
    def __repr__(self):
        return "<StatsRecentViews(id=%r, session_id=%r, artifact_group_id=%r, user_id=%r,view_count=%r)>" % (self.id, self.session_id, self.artifact_group_id, self.user_id, self.view_count)

class ArtifactRequests(db.Model):
    __tablename__ = "artifact_requests"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    artifact_group_id = db.Column(db.Integer, db.ForeignKey("artifact_groups.id", ondelete='CASCADE'), nullable=False)
    requester_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete='CASCADE'), nullable=False)
    project = db.Column(db.String(2048), nullable=False)
    project_description = db.Column(db.String(2048), nullable=False)
    researchers = db.Column(db.String(2048), nullable=False)
    representative_researcher_email = db.Column(db.String(2048), nullable=False)
    agreement_file = db.Column(db.LargeBinary, nullable=False)
    irb = db.Column(db.LargeBinary, nullable=True)
    ticket_id = db.Column(db.Integer, nullable=True)
    frgp_data = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return "<ArtifactRequests(id=%r, artifact_group_id=%r, requester_user_id=%r, research_desc=%r, research_that_interacts=%r, agreement_file=%r)>" % (self.id, self.artifact_group_id, self.requester_user_id, self.research_desc, self.research_that_interacts, self.agreement_file)

class Labels(db.Model):
    __tablename__ = "labels"
    
    label_id = db.Column(db.String(128),primary_key=True, nullable=False)
    artifact_id = db.Column(db.Integer, db.ForeignKey("artifacts.artifact_group_id", ondelete='CASCADE'), nullable=False)
    label_url = db.Column(db.String(2048), nullable=False)

    def __repr__(self):
        return "<Labels(label_id=%r, artifact_id=%r, label_url=%r)>" % (self.label_id, self.artifact_id, self.label_url)

class ProviderPermissions(db.Model):
    #Each row contains a user_id,provider pair which indicates that a user can contribute a dataset under this provider
    __tablename__ = "provider_permissions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete='CASCADE'), nullable=False)
    provider = db.Column(db.String(1024), db.ForeignKey("dua.provider", ondelete='CASCADE'), nullable=False)
    collection = db.Column(db.String(1024), db.ForeignKey("dua.collection", ondelete='CASCADE'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("user_id","provider","collection"),)
    
class ContributedArtifacts(db.Model):
    #Each row contains a user_id,provider pair which indicates that a user can contribute a dataset under this provider
    __tablename__ = "contributed_artifacts"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete='CASCADE'), nullable=False)
    title = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f"<ContributedArtifacts(id={self.id}, user_id={self.user_id}, artifact_title='{self.artifact_title}')>"