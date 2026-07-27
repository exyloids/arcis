"""Background tasks for Gmail synchronization."""

from celery import shared_task

from arcis_backend.candidates import CandidateService
from arcis_backend.gmail_artifacts import GmailArtifactRepository
from arcis_backend.gmail_oauth import GmailOAuthService
from arcis_backend.ledger import database_engine
from arcis_backend.mailboxes import CredentialCipher, MailboxService
from arcis_backend.settings import get_settings
from arcis_backend.storage import MinioArtifactStorage
from arcis_backend.sync_jobs import GmailSyncJobService


def _services():
    settings = get_settings()
    engine = database_engine(settings.database_url)
    storage = MinioArtifactStorage(settings.object_storage_endpoint, settings.object_storage_access_key, settings.object_storage_secret_key, settings.object_storage_bucket)
    mailboxes = MailboxService(engine, settings.demo_user_id, CredentialCipher(settings.credential_encryption_key_version, settings.credential_encryption_key))
    oauth = GmailOAuthService(engine, settings.demo_user_id, mailboxes, settings.gmail_oauth_client_id, settings.gmail_oauth_client_secret, settings.gmail_oauth_redirect_uri)
    return GmailSyncJobService(engine, settings.demo_user_id), mailboxes, oauth, GmailArtifactRepository(engine, settings.demo_user_id, storage), CandidateService(engine, settings.demo_user_id)


@shared_task(name="arcis.gmail.run_next")
def run_next_gmail_sync():
    jobs, mailboxes, oauth, artifacts, candidates = _services()
    result = jobs.run_next(mailboxes, oauth, artifacts, candidates)
    return str(result["id"]) if result else None


@shared_task(name="arcis.gmail.enqueue_daily")
def enqueue_daily_gmail_syncs():
    jobs, mailboxes, _, _, _ = _services()
    queued = [jobs.request_sync(mailbox["id"])["id"] for mailbox in mailboxes.list_mailboxes() if mailbox["connection_status"] == "connected"]
    for _ in queued:
        run_next_gmail_sync.delay()
    return [str(job_id) for job_id in queued]
