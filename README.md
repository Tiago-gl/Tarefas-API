# API de Tarefas

Este projeto e uma API Flask para cadastro e ordenacao de tarefas. A API garante que o campo `ordem_apresentacao` seja sempre sequencial (1..N), inclusive apos exclusoes e trocas de posicao.

## Requisitos

- Python 3.11+ (ou a versao indicada em `.python_version`)
- Banco Postgres (ex: Supabase)

## Passo a passo (execucao local)

1) Crie e ative um ambiente virtual

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2) Instale as dependencias

```powershell
pip install -r requirements.txt
```

3) Configure as variaveis de ambiente

Crie um arquivo `.env` na raiz do projeto com a variavel `DATABASE_URL`:

```env
DATABASE_URL="postgresql://USER:SENHA@HOST:PORT/DB"
```

Opcional: defina `WEB_ORIGIN` para restringir o CORS (padrao: `*`).

4) Garanta a estrutura da tabela

Estrutura minima esperada (ajuste nomes/tipos se seu banco ja existir):

```sql
CREATE TABLE IF NOT EXISTS tarefas (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL UNIQUE,
  custo NUMERIC NOT NULL,
  data_limite DATE NOT NULL,
  ordem_apresentacao INTEGER NOT NULL UNIQUE
);
```

5) Execute a API

```powershell
python app.py
```

A API sobe por padrao em `http://127.0.0.1:5000`.

## Endpoints

- `GET /api/health`
  - Healthcheck.

- `GET /api/tarefas`
  - Lista tarefas ordenadas por `ordem_apresentacao`.

- `POST /api/tarefas`
  - Cria tarefa. Se `ordem_apresentacao` nao for enviado, a API usa o proximo numero disponivel.
  - Body JSON:
    ```json
    {
      "nome": "Tarefa A",
      "custo": 10.5,
      "data_limite": "2026-01-31",
      "ordem_apresentacao": 1
    }
    ```

- `PUT /api/tarefas/{id}`
  - Atualiza `nome`, `custo` e `data_limite`.

- `DELETE /api/tarefas/{id}`
  - Exclui a tarefa e renumera a ordem para manter a sequencia (1..N).

- `PATCH /api/tarefas/{id}/mover`
  - Troca a posicao com o vizinho de cima ou de baixo.
  - Body JSON:
    ```json
    { "direction": "up" }
    ```
    ou
    ```json
    { "direction": "down" }
    ```

## Como funciona a ordenacao

- Na criacao sem `ordem_apresentacao`, a API pega o maior valor atual e soma 1.
- Ao mover (`/mover`), a API troca a ordem da tarefa com o vizinho imediatamente acima/abaixo.
- Ao excluir, a API renumera todas as tarefas pela ordem atual para remover buracos na sequencia.

## Observacoes

- O campo `nome` e unico.
- O campo `ordem_apresentacao` e unico e controlado pela API.
- Se houver conflito de unicidade, a API retorna erro 409.