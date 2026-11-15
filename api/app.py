from botocore.exceptions import ClientError
from flask import Flask, request, jsonify
from flask_cors import CORS
import pymysql
import boto3
import os
import uuid
from datetime import datetime

app = Flask(__name__)
CORS(app)

# --- Config (from environment variables, set on the EC2 instance) ---
DB_HOST = os.environ.get("DB_HOST")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME", "studyvault")
S3_BUCKET = os.environ.get("S3_BUCKET")
AWS_REGION = os.environ.get("AWS_REGION", "eu-central-1")

s3 = boto3.client("s3", region_name=AWS_REGION)

def get_db_connection():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )

def init_db():
    connection = get_db_connection()
    with connection.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                content TEXT,
                file_url VARCHAR(500),
                created_at DATETIME
            )
        """)
    connection.commit()
    connection.close()

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/api/notes", methods=["GET"])
def get_notes():
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM notes ORDER BY created_at DESC")
        notes = cursor.fetchall()
    conn.close()

    for note in notes:
        if note.get("file_url"):
            try:
                note["file_url"] = s3.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': S3_BUCKET, 'Key': note["file_url"]},
                    ExpiresIn=300
                )
            except ClientError:
                note["file_url"] = None

    return jsonify(notes), 200

@app.route("/api/notes", methods=["POST"])
def create_note():
    title = request.form.get("title")
    content = request.form.get("content")
    file = request.files.get("file")

    file_url = None
    if file:
        file_key = f"{uuid.uuid4()}-{file.filename}"
        s3.upload_fileobj(file, S3_BUCKET, file_key)

    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO notes (title, content, file_url, created_at) VALUES (%s, %s, %s, %s)",
            (title, content, file_key, datetime.utcnow())
        )
    conn.commit()
    conn.close()
    return jsonify({"message": "Note created"}), 201

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)