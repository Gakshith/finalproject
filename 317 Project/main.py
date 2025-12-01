from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import os
import httpx

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    status,
    Request,
    Query,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from sqlalchemy.orm import Session
from sqlalchemy import text

from jose import JWTError, jwt
from passlib.context import CryptContext
from dotenv import load_dotenv  

from database import Base, engine, get_db
import schemas
import models  

load_dotenv()


app = FastAPI(title="Movie Review API with JWT + TMDb")

# --------------------- CORS ---------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables if not exist
Base.metadata.create_all(bind=engine)


# --------------------- JWT CONFIG ---------------------
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is not set")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

security = HTTPBearer(auto_error=False)

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta if expires_delta else timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# --------------------- TMDb CONFIG ---------------------
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


# --------------------- AUTH HELPERS ---------------------
async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    token = None
    if credentials:
        token = credentials.credentials

    if not token:
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated (no token provided)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    sql = text("""
        SELECT id, username, email, full_name, bio, profile_picture, created_at
        FROM users
        WHERE username = :username
        LIMIT 1;
    """)
    row = db.execute(sql, {"username": username}).mappings().first()

    if not row:
        raise credentials_exception

    return dict(row)


# --------------------- AUTH ROUTES ---------------------
@app.post("/signup")
async def signup(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    try:
        check_sql = text("""
            SELECT id FROM users
            WHERE username = :username OR email = :email
            LIMIT 1;
        """)
        existing = db.execute(
            check_sql,
            {"username": user_in.username, "email": user_in.email},
        ).first()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username or email already exists",
            )

        insert_sql = text("""
            INSERT INTO users (username, email, user_password, full_name, bio, profile_picture)
            VALUES (:username, :email, :user_password, :full_name, :bio, :profile_picture);
        """)

        db.execute(
            insert_sql,
            {
                "username": user_in.username,
                "email": user_in.email,
                "user_password": hash_password(user_in.password),
                "full_name": user_in.full_name,
                "bio": user_in.bio,
                "profile_picture": str(user_in.profile_picture) if user_in.profile_picture else None,
            },
        )
        db.commit()

        return {"message": "User created successfully!"}

    except HTTPException:
        raise
    except Exception as e:
        print("Signup Error:", e)
        raise HTTPException(status_code=500, detail="Signup failed")

# //to get the all the data from the db
@app.get("/debug/all")
async def debug_users(db: Session = Depends(get_db)):
    users = db.execute(text("SELECT * FROM users")).mappings().all()
    
    # Fetch movies
    movies = db.execute(text("SELECT * FROM movies")).mappings().all()
    
    # Fetch reviews
    reviews = db.execute(text("SELECT * FROM reviews")).mappings().all()

    return {
        "users": [dict(u) for u in users],
        "movies": [dict(m) for m in movies],
        "reviews": [dict(r) for r in reviews],
    }

@app.post("/login", response_model=schemas.Token)
async def login(user_in: schemas.UserLogin, db: Session = Depends(get_db)):
    try:
        sql = text("""
            SELECT id, username, email, user_password
            FROM users
            WHERE username = :username
            LIMIT 1;
        """)
        result = db.execute(sql, {"username": user_in.username})
        row = result.mappings().first()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect username or password",
            )

        if not verify_password(user_in.password, row["user_password"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect username or password",
            )

        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": row["username"]},
            expires_delta=access_token_expires,
        )

        return {"access_token": access_token, "token_type": "bearer"}

    except HTTPException:
        raise
    except Exception as e:
        print("Login Error:", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed",
        )


@app.get("/me", response_model=schemas.UserRead)
async def read_profile(current_user: dict = Depends(get_current_user)):
    return schemas.UserRead(**current_user)


# --------------------- MOVIE ROUTES ---------------------
@app.post("/movies/{tmdb_movie_id}", response_model=schemas.MovieRead)
async def adding_movie(
    tmdb_movie_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    external_id = str(tmdb_movie_id)

    # Check if this user already saved this movie
    find_movie_query = text("""
        SELECT id, external_id, title, year, poster_url, overview, genres, user_id
        FROM movies
        WHERE user_id = :user_id
          AND external_id = :external_id
        LIMIT 1;
    """)

    find_movie = db.execute(
        find_movie_query,
        {
            "user_id": current_user["id"],
            "external_id": external_id,
        },
    ).mappings().first()

    if find_movie:
        # movie already in this user's list
        return schemas.MovieRead(**find_movie)

    # Fetch from TMDb since user doesn't have it
    if not TMDB_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="TMDb API key not configured",
        )

    tmdb_url = f"{TMDB_BASE_URL}/movie/{external_id}"
    params = {
        "api_key": TMDB_API_KEY,    # expecting v3 key here
        "language": "en-US",
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(tmdb_url, params=params)
        data = resp.json()

        if resp.status_code != 200:
            print("TMDb movie error:", data)
            raise HTTPException(status_code=500, detail="TMDb API error")

        title = data.get("title") or data.get("name") or "Unknown"

        year = None
        if data.get("release_date"):
            try:
                year = int(data["release_date"].split("-")[0])
            except Exception:
                year = None

        poster = (
            f"{TMDB_IMAGE_BASE}{data.get('poster_path')}"
            if data.get("poster_path")
            else None
        )

        overview = data.get("overview") or ""

        genres_list = data.get("genres") or []
        genres = ", ".join(g["name"] for g in genres_list if g.get("name"))

        # Insert movie for this user
        insert_sql = text("""
            INSERT INTO movies (external_id, title, year, poster_url, overview, genres, user_id)
            VALUES (:external_id, :title, :year, :poster_url, :overview, :genres, :user_id);
        """)

        db.execute(
            insert_sql,
            {
                "external_id": external_id,
                "title": title,
                "year": year,
                "poster_url": poster,
                "overview": overview,
                "genres": genres,
                "user_id": current_user["id"],
            },
        )
        db.commit()

        movie = db.execute(
            find_movie_query,
            {
                "user_id": current_user["id"],
                "external_id": external_id,
            },
        ).mappings().first()

        return schemas.MovieRead(**movie)

    except HTTPException:
        raise
    except Exception as e:
        print("Error adding movie:", e)
        raise HTTPException(status_code=500, detail="Failed to add movie")


@app.get("/movies/tmdb/{tmdb_movie_id}/reviews", response_model=List[schemas.ReviewRead])
async def get_movie_reviews_by_tmdb(
    tmdb_movie_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    external_id = str(tmdb_movie_id)

    find_movie_query = text("""
        SELECT id
        FROM movies
        WHERE user_id = :user_id
          AND external_id = :external_id
        LIMIT 1;
    """)
    movie_row = db.execute(
        find_movie_query,
        {
            "user_id": current_user["id"],
            "external_id": external_id,
        },
    ).mappings().first()

    if not movie_row:
        raise HTTPException(
            status_code=404,
            detail="Movie not found for this user. Add it first.",
        )

    movie_id = movie_row["id"]

    reviews_sql = text("""
        SELECT id, user_id, movie_id, rating, comment, likes, created_at
        FROM reviews
        WHERE movie_id = :movie_id
        ORDER BY created_at DESC;
    """)
    rows = db.execute(
        reviews_sql,
        {"movie_id": movie_id},
    ).mappings().all()

    return [schemas.ReviewRead(**row) for row in rows]


# --------------------- REVIEW ROUTES ---------------------
@app.post("/reviews", response_model=schemas.ReviewRead)
async def add_review(
    review_in: schemas.ReviewCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 1) Make sure the movie exists in movies table
    movie_check_sql = text("""
        SELECT id 
        FROM movies 
        WHERE id = :movie_id
        LIMIT 1;
    """)
    movie_row = db.execute(
        movie_check_sql, {"movie_id": review_in.movie_id}
    ).mappings().first()

    if not movie_row:
        raise HTTPException(
            status_code=404,
            detail="Movie not found — add the movie first.",
        )

    # 2) Check if THIS USER already reviewed THIS MOVIE
    review_check_sql = text("""
        SELECT id, user_id, movie_id, rating, comment, likes, created_at
        FROM reviews
        WHERE user_id = :user_id
          AND movie_id = :movie_id
        LIMIT 1;
    """)

    existing = db.execute(
        review_check_sql,
        {
            "user_id": current_user["id"],
            "movie_id": review_in.movie_id,
        },
    ).mappings().first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="You already reviewed this movie.",
        )

    # 3) Insert new review
    insert_sql = text("""
        INSERT INTO reviews (user_id, movie_id, rating, comment, likes)
        VALUES (:user_id, :movie_id, :rating, :comment, 0);
    """)

    db.execute(
        insert_sql,
        {
            "user_id": current_user["id"],
            "movie_id": review_in.movie_id,
            "rating": review_in.rating,
            "comment": review_in.comment,
        },
    )
    db.commit()

    new_review = db.execute(
        review_check_sql,
        {
            "user_id": current_user["id"],
            "movie_id": review_in.movie_id,
        },
    ).mappings().first()

    return schemas.ReviewRead(**new_review)


@app.put("/reviews/{movie_id}", response_model=schemas.ReviewRead)
async def update_review(
    movie_id: int,
    review_in: schemas.ReviewCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update the current user's review for a specific movie.
    """

    review_check_sql = text("""
        SELECT id, user_id, movie_id, rating, comment, likes, created_at
        FROM reviews
        WHERE user_id = :user_id
          AND movie_id = :movie_id
        LIMIT 1;
    """)

    existing = db.execute(
        review_check_sql,
        {
            "user_id": current_user["id"],
            "movie_id": movie_id,
        },
    ).mappings().first()

    if not existing:
        raise HTTPException(
            status_code=404,
            detail="You have not reviewed this movie yet.",
        )

    update_sql = text("""
        UPDATE reviews
        SET rating = :rating,
            comment = :comment
        WHERE id = :id;
    """)

    db.execute(
        update_sql,
        {
            "rating": review_in.rating,
            "comment": review_in.comment,
            "id": existing["id"],
        },
    )
    db.commit()

    updated = db.execute(
        review_check_sql,
        {
            "user_id": current_user["id"],
            "movie_id": movie_id,
        },
    ).mappings().first()

    return schemas.ReviewRead(**updated)


@app.delete("/reviews/{movie_id}")
async def delete_review(
    movie_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete the current user's review for this movie.
    """

    review_check_sql = text("""
        SELECT id
        FROM reviews
        WHERE user_id = :user_id
          AND movie_id = :movie_id
        LIMIT 1;
    """)

    review_row = db.execute(
        review_check_sql,
        {
            "user_id": current_user["id"],
            "movie_id": movie_id,
        },
    ).mappings().first()

    if not review_row:
        raise HTTPException(
            status_code=404,
            detail="You have not reviewed this movie yet.",
        )

    delete_sql = text("""
        DELETE FROM reviews
        WHERE id = :review_id;
    """)

    db.execute(
        delete_sql,
        {"review_id": review_row["id"]},
    )
    db.commit()

    return {"detail": "Review deleted successfully."}


# --------------------- PROFILE UPDATE ROUTE ---------------------
@app.put("/me")
async def update_profile_all(
    payload: schemas.UserUpdateProfile,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Single endpoint to update username, full_name, bio, profile_picture.
    User can send any subset of fields.
    If username changes, we also return a new JWT.
    """

    try:
        new_username = current_user["username"]
        new_full_name = current_user["full_name"]
        new_bio = current_user["bio"]
        new_profile_picture = current_user["profile_picture"]

        # Overwrite only if user sent a new value
        if payload.username is not None:
            new_username = payload.username.strip()

        if payload.full_name is not None:
            new_full_name = payload.full_name

        if payload.bio is not None:
            new_bio = payload.bio

        if payload.profile_picture is not None:
            new_profile_picture = str(payload.profile_picture)

        username_changed = new_username != current_user["username"]

        if username_changed:
            if not new_username:
                raise HTTPException(
                    status_code=400,
                    detail="Username cannot be empty",
                )

            check_sql = text("""
                SELECT id
                FROM users
                WHERE username = :username
                LIMIT 1;
            """)
            existing = db.execute(
                check_sql,
                {"username": new_username},
            ).mappings().first()

            if existing and existing["id"] != current_user["id"]:
                raise HTTPException(
                    status_code=400,
                    detail="Username already taken",
                )

        update_sql = text("""
            UPDATE users
            SET username = :username,
                full_name = :full_name,
                bio = :bio,
                profile_picture = :profile_picture
            WHERE id = :user_id;
        """)

        db.execute(
            update_sql,
            {
                "username": new_username,
                "full_name": new_full_name,
                "bio": new_bio,
                "profile_picture": new_profile_picture,
                "user_id": current_user["id"],
            },
        )
        db.commit()

        fetch_sql = text("""
            SELECT id, username, email, full_name, bio, profile_picture, created_at
            FROM users
            WHERE id = :user_id
            LIMIT 1;
        """)

        row = db.execute(
            fetch_sql,
            {"user_id": current_user["id"]},
        ).mappings().first()

        user_out = schemas.UserRead(**row)

        new_token = None
        token_type = None
        if username_changed:
            access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            new_token = create_access_token(
                data={"sub": new_username},
                expires_delta=access_token_expires,
            )
            token_type = "bearer"

        return {
            "detail": "Profile updated successfully",
            "user": user_out,
            "access_token": new_token,   # null if username didn't change
            "token_type": token_type,
        }

    except HTTPException:
        raise
    except Exception as e:
        print("Update profile error:", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to update profile",
        )
