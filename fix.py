content = open('lexai/backend/Dockerfile').read()
content = content.replace('CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]', 'CMD sh -c "uvicorn main:app --host 0.0.0.0 --port \"')
open('lexai/backend/Dockerfile', 'w').write(content)
print('OK')
