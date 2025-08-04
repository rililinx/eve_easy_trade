

# 📦 EVE Online Market Arbitrage Tool

This project aims to analyze price differences across EVE Online trade hubs and suggest the most profitable buy-sell item routes based on player-specific constraints (wallet, cargo volume, region access).

The architecture is built on microservices in Python and orchestrated using Docker Compose. Price data is fetched from the EVE Swagger Interface (ESI) and stored temporarily in Redis.

---

## 🧱 Architecture Overview

* **Frontend (UI)**: Streamlit or React app for user interaction
* **Microservices**:
  * **Price Loader**: Fetches market prices from ESI
  * **Calculator**: Identifies profitable trade opportunities
  * **Jump Graph Generator**: Calculates static jump distances between regions
* **Database**: Redis (lightweight and supports TTL)
* **Orchestration**: Docker Compose

---

## 🔧 Default Settings

| Parameter        | Default                                                     | Description                                |
| ---------------- | ----------------------------------------------------------- | ------------------------------------------ |
| Regions          | Jita, Rens, Dodixie, Hek, Amarr, Ashab, Botane, Sinq Laison | Can be extended via UI                     |
| Security Limit   | 0.5                                                         | Only considers high-sec systems by default |
| Cargo Volume     | 230 m³                                                      | Total transport capacity                   |
| Wallet Amount    | 50,000,000 ISK                                              | Maximum purchase budget                    |
| Profit Threshold | 500,000 ISK                                                 | Minimum profit to be considered            |

---

## 🚀 Implementation Plan

### **Phase 1: Project Initialization & Static Data**

**Tasks:**

* [x] Set up Python project with Docker Compose
* [x] Initialize Redis container for storage
* [x] Create shared data service or volume for static files
* [x] Load and store static item list from ESI (names, volumes, IDs)
* [x] Load full region list from ESI for dropdown input in UI

---

### **Phase 2: Jump Graph Calculation**

**Tasks:**

* [ ] Use ESI to fetch shortest route (jump count) between trade hubs
* [ ] Precompute all jump combinations between selected regions
* [ ] Store results in Redis or JSON file
* [ ] This data is static and only needs to be calculated once

---

### **Phase 3: Price Loader Microservice**

**Tasks:**

* [ ] Use ESI API to fetch buy/sell orders per region
* [ ] Extract and store best buy/sell prices per item per region
* [ ] Store data in Redis with TTL of 1 hour
* [ ] Schedule data updates every 15 minutes (optional: background job)
* [ ] Implement manual refresh trigger via HTTP endpoint

---

### **Phase 4: Calculator Microservice**

**Tasks:**

* [ ] Fetch current prices, jump distances, item volumes from Redis
* [ ] Loop through all region pairs and item combinations
* [ ] Calculate:

  * Max affordable quantity
  * Total cost and volume
  * Expected revenue
  * Profit, profit per jump
* [ ] Filter results by:

  * User wallet amount
  * Cargo volume
  * Profit threshold
* [ ] Return top trade opportunities as structured JSON

---

### **Phase 5: User Interface (UI)**

**Tasks:**

* [ ] Build UI with Streamlit (or React if preferred)
* [ ] Allow user to:

  * Add custom regions (from dropdown)
  * Set custom wallet and cargo values
  * Trigger price update
  * Trigger trade recalculation
* [ ] Display results in sortable table:

  * Item name
  * Buy/sell region
  * Volume, quantity, price
  * Jumps, profit, profit/jump
* [ ] Add loader status and error notifications

---

### **Phase 6: Orchestration with Docker Compose**

**Tasks:**

* [ ] Create Dockerfiles for each microservice
* [ ] Define services and networking in `docker-compose.yml`
* [ ] Mount shared volume if needed for static data
* [ ] Expose relevant ports (e.g. UI and Redis)

---

## 🔁 Optional Enhancements

* [ ] Notification system for high-profit opportunities
* [ ] Historical tracking of top trades
* [ ] Authentication for multi-user support
* [ ] Item exclusion filter (e.g., ignore minerals or blueprints)
* [ ] Export results to CSV

---

## 🗃 Example Output (JSON)

```json
{
  "item": "Tritanium",
  "buy_region": "Jita",
  "sell_region": "Dodixie",
  "volume": 3.0,
  "amount": 5000,
  "total_cost": 1200000,
  "profit": 800000,
  "jumps": 10,
  "profit_per_jump": 80000
}
```

---

## 📦 Project Folder Structure (Suggested)

```
eve-arbitrage/
├── docker-compose.yml
├── price_loader/
│   └── price_loader.py
├── calculator/
│   └── calculator.py
├── jump_graph/
│   └── build_graph.py
├── ui/
│   └── app.py
├── shared/
│   └── static_data/
├── .env
└── README.md
```

---

Let me know if you'd like this turned into a GitHub-ready template with working starter code.
