

def test_download_endpoint_serves_file(tmp_path):
    from app import app as flask_app

    # Готовим временный uploads с одним txt-файлом
    old_upload = flask_app.config.get('UPLOAD_FOLDER')
    try:
        uploads_dir = tmp_path / 'uploads'
        uploads_dir.mkdir(parents=True, exist_ok=True)
        f = uploads_dir / 'readme.txt'
        f.write_text('hello', encoding='utf-8')
        flask_app.config['UPLOAD_FOLDER'] = str(uploads_dir)

        with flask_app.test_client() as client:
            resp = client.get('/download/readme.txt')
            assert resp.status_code == 200
            assert resp.data == b'hello'
            # неподдерживаемое расширение
            (uploads_dir / 'secret.bin').write_bytes(b'42')
            resp2 = client.get('/download/secret.bin')
            assert resp2.status_code in (400, 403)
    finally:
        flask_app.config['UPLOAD_FOLDER'] = old_upload
