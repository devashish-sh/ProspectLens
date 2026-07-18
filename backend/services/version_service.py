# backend/services/version_service.py
# ProspectLens — Dynamic Lead Versioning & History Service

import json
from datetime import datetime
from sqlmodel import Session
from database.models import Lead, LeadVersionHistory

class VersionService:
    """
    Manages lead versions and version history logging.
    Ensures that any changes to lead fields automatically increment the lead's version number.
    """

    @staticmethod
    def record_creation(session: Session, lead: Lead):
        """
        Logs the initial version 1 entry for a newly created lead.
        """
        lead.version = 1
        session.add(lead)
        session.flush()

        # Log creation history entry
        history = LeadVersionHistory(
            lead_id=lead.lead_id,
            previous_version=0,
            new_version=1,
            action_type="created",
            modified_fields=json.dumps(["all_fields"]),
            created_at=datetime.utcnow()
        )
        session.add(history)
        print(f"[Version] Lead {lead.lead_id} version history created at version 1")

    @staticmethod
    def record_version(session: Session, lead: Lead, action_type: str, modified_fields: list) -> int:
        """
        Increments the lead's version number and logs a version history entry.
        """
        previous_version = lead.version or 1
        new_version = previous_version + 1

        lead.version = new_version
        lead.updated_at = datetime.utcnow()
        session.add(lead)
        session.flush()

        # Log version update history entry
        fields_str = json.dumps(modified_fields) if modified_fields else json.dumps([])
        history = LeadVersionHistory(
            lead_id=lead.lead_id,
            previous_version=previous_version,
            new_version=new_version,
            action_type=action_type,
            modified_fields=fields_str,
            created_at=datetime.utcnow()
        )
        session.add(history)
        print(f"[Version] Lead {lead.lead_id} version history recorded: {previous_version} -> {new_version} via '{action_type}'")
        return new_version
