"""Interface graphique temps réel du logisticien (TP6 - Streaming RabbitMQ).

Consomme les événements de la file RabbitMQ dans un thread dédié (car `start_consuming()`
est bloquant) et expose un tableau de bord web actualisé en direct.
"""
import os
from contextlib import asynccontextmanager
from threading import Event, Thread

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from app.streaming import DEFAULT_QUEUE_NAME
from streaming.consumer import OrderQueueState, consume_forever

queue_state = OrderQueueState()
_stop_event = Event()

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <title>Logisticien — Livraisons du jour (Streaming)</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; background: #f8fafc; color: #0f172a; }
    h1 { margin-bottom: 0.25rem; }
    .subtitle { color: #475569; margin-bottom: 1.5rem; }
    .kpis { display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
    .card { background: #fff; padding: 1rem 1.25rem; border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08); min-width: 160px; }
    .card .val { font-size: 1.75rem; font-weight: 700; }
    table { width: 100%; border-collapse: collapse; background: #fff;
            border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
    th, td { padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid #e2e8f0; }
    th { background: #f1f5f9; font-size: 0.85rem; text-transform: uppercase; color: #475569; }
    .badge { padding: 0.2rem 0.6rem; border-radius: 999px; font-weight: 600; font-size: 0.8rem; }
    .oui { background: #dcfce7; color: #166534; }
    .non { background: #fee2e2; color: #991b1b; }
    .done { opacity: 0.55; }
    button { padding: 0.35rem 0.75rem; border: 1px solid #cbd5e1; border-radius: 6px;
             background: #fff; cursor: pointer; }
    button:hover { background: #f1f5f9; }
  </style>
</head>
<body>
  <h1>Interface Logisticien — Préparation des livraisons</h1>
  <p class="subtitle">Flux temps réel RabbitMQ (file <code>delivery_orders</code>)</p>
  <div class="kpis">
    <div class="card"><div>Total reçues</div><div class="val" id="total">0</div></div>
    <div class="card"><div>Express aujourd'hui</div><div class="val" id="express">0</div></div>
    <div class="card"><div>Standard</div><div class="val" id="standard">0</div></div>
    <div class="card"><div>Préparées</div><div class="val" id="prepared">0</div></div>
  </div>
  <table>
    <thead>
      <tr>
        <th>Commande</th><th>Express</th><th>Probabilité</th>
        <th>Zone</th><th>Distance</th><th>Poids</th><th>Météo</th><th>Client</th><th>Action</th>
      </tr>
    </thead>
    <tbody id="rows"></tbody>
  </table>
  <script>
    // Les messages viennent du réseau : on échappe tout avant de l'insérer dans la page (XSS)
    function esc(value) {
      return String(value ?? '-').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      })[c]);
    }
    async function prepare(orderId) {
      await fetch(`/api/orders/${encodeURIComponent(orderId)}/prepare`, { method: 'POST' });
      refresh();
    }
    async function refresh() {
      const res = await fetch('/api/orders');
      const data = await res.json();
      document.getElementById('total').textContent = data.total;
      document.getElementById('express').textContent = data.express_count;
      document.getElementById('standard').textContent = data.standard_count;
      document.getElementById('prepared').textContent = data.prepared_count;
      const tbody = document.getElementById('rows');
      tbody.innerHTML = data.orders.map(o => `
        <tr class="${o.prepared ? 'done' : ''}">
          <td><strong>${esc(o.order_id)}</strong></td>
          <td><span class="badge ${o.express_eligible ? 'oui' : 'non'}">${esc(o.decision)}</span></td>
          <td>${o.probability != null ? `${(Number(o.probability) * 100).toFixed(1)} %` : '-'}</td>
          <td>${esc(o.delivery_zone)}</td>
          <td>${esc(o.distance_km)} km</td>
          <td>${esc(o.weight_kg)} kg</td>
          <td>${esc(o.weather)}</td>
          <td>${esc(o.customer_type)}</td>
          <td>${o.prepared ? 'Préparée ✓'
                : `<button data-id="${esc(o.order_id)}" onclick="prepare(this.dataset.id)">Préparer</button>`}</td>
        </tr>`).join('');
    }
    refresh();
    setInterval(refresh, 1500);
  </script>
</body>
</html>
"""


@asynccontextmanager
async def lifespan(_app: FastAPI):
    rabbitmq_url = os.getenv("RABBITMQ_URL")
    queue_name = os.getenv("RABBITMQ_QUEUE", DEFAULT_QUEUE_NAME)
    thread = None
    if rabbitmq_url:
        _stop_event.clear()
        thread = Thread(
            target=consume_forever,
            args=(rabbitmq_url, queue_state, queue_name, _stop_event),
            daemon=True,
        )
        thread.start()
    yield
    _stop_event.set()
    if thread is not None:
        thread.join(timeout=2)


app = FastAPI(title="Interface Logisticien (Streaming)", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return DASHBOARD_HTML


@app.get("/api/orders")
def list_orders() -> dict:
    return queue_state.snapshot()


@app.post("/api/orders/{order_id}/prepare")
def prepare_order(order_id: str) -> dict:
    if not queue_state.mark_prepared(order_id):
        raise HTTPException(status_code=404, detail=f"Commande introuvable : {order_id}")
    return {"order_id": order_id, "prepared": True}
