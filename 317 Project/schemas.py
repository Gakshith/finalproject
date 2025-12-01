from pydantic import BaseModel, EmailStr, HttpUrl
from typing import Optional

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str  
    full_name: Optional[str] = None
    bio: Optional[str] = None
    profile_picture: Optional[HttpUrl] = None

class UserLogin(BaseModel):
    username : str
    password: str
        

class UserRead(BaseModel):
    id: int
    username: str
    email: EmailStr
    full_name: Optional[str]
    bio: Optional[str]
    profile_picture: Optional[str]
    created_at: Optional[str]

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None

class MovieBase(BaseModel):
    title: str
    year: Optional[int] = None
    poster_url: Optional[str] = None
    overview: Optional[str] = None
    genres: Optional[str] = None


class MovieCreate(MovieBase):
    external_id: str


class MovieRead(MovieBase):
    id: int
    external_id: str
    user_id: Optional[int]  

    class Config:
        from_attributes = True


class ReviewCreate(BaseModel):
    movie_id: int
    rating: float
    comment: Optional[str] = None


class ReviewRead(BaseModel):
    id: int
    user_id: int
    movie_id: int
    rating: float
    comment: Optional[str]
    likes: int
    created_at: Optional[str]

    class Config:
        from_attributes = True


class MovieDetail(MovieRead):
    reviews: List[ReviewRead] = []

class UserUpdateProfile(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    bio: Optional[str] = None
    profile_picture: Optional[HttpUrl] = None