"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List

# Coaching lead management schemas

EXAM_CHOICES = [
    "IIT JEE", "NEET", "UPSC", "SSC", "CAT", "CLAT", "GATE", "BANKING", "RAILWAYS", "FOUNDATION"
]

class Location(BaseModel):
    lat: Optional[float] = Field(None, description="Latitude")
    lng: Optional[float] = Field(None, description="Longitude")

class Coaching(BaseModel):
    """
    Coaching listings
    Collection name: "coaching"
    """
    name: str = Field(..., description="Coaching institute name")
    city: str = Field(..., description="City name (e.g., Jaipur, Delhi)")
    exams: List[str] = Field(default_factory=list, description="Exams covered e.g. IIT JEE, NEET")
    size: Optional[int] = Field(None, ge=0, description="Estimated student count or capacity")
    address: Optional[str] = Field(None, description="Full street address")
    phone: Optional[str] = Field(None, description="Primary phone number")
    website: Optional[str] = Field(None, description="Website URL")
    google_maps_url: Optional[str] = Field(None, description="Google Maps listing URL")
    images: List[str] = Field(default_factory=list, description="Image URLs")
    location: Optional[Location] = None
    description: Optional[str] = Field(None, description="Short description or highlights")
    status: str = Field("neutral", description="Lead disposition: neutral|liked|disliked")

class Note(BaseModel):
    """
    Notes for a coaching lead (meetings, follow-ups, actions)
    Collection name: "note"
    """
    coaching_id: str = Field(..., description="Related coaching document ID")
    title: Optional[str] = Field(None, description="Short title e.g. First Meet")
    content: Optional[str] = Field(None, description="What happened / key details")
    stage: Optional[str] = Field(None, description="first_meet | second_meet | followup | other")
    next_action: Optional[str] = Field(None, description="What to do next")
    next_action_date: Optional[str] = Field(None, description="YYYY-MM-DD or natural text")
