# 1. Escolhe uma versão oficial e leve do Python
FROM python:3.11-slim

# 2. Define a pasta de trabalho DENTRO do container
WORKDIR /app

# 3. Copia o arquivo de dependências primeiro (otimiza o tempo de build)
COPY backend/requirements.txt ./backend/

# 4. Instala as dependências do FastAPI
RUN pip install --no-cache-dir -r backend/requirements.txt

# 5. Copia o resto do código do backend e o frontend para o container
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# (Nota: Com essa estrutura, o seu Path(__file__).resolve().parent.parent.parent / "frontend"
# vai apontar exatamente para /app/frontend, funcionando perfeitamente!)

# 6. Informa que o container vai usar a porta 8000
EXPOSE 8000

# 7. Muda para a pasta do backend antes de rodar o comando
WORKDIR /app/backend

# 8. O comando que roda quando o container ligar
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]