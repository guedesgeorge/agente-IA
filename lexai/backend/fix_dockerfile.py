with open('Dockerfile', 'r') as f:
    content = f.read()

content = content.replace('CMD sh -c "uvicorn main:app --host 0.0.0.0 --port "', 'CMD sh -c "uvicorn main:app --host 0.0.0.0 --port "')

with open('Dockerfile', 'w') as f:
    f.write(content)

print('OK - Dockerfile corrigido')
