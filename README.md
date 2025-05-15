# pypekit

A lightweight, **type‑directed** pipeline framework for Python that lets you stitch together small, single‑responsibility *Tasks* into reproducible, cached *Pipelines*. Examples can be found in [`here`](./examples).

---

## ✨ Key features

| Feature                          | What it means for you                                                                                                                          |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **Type‑aware chaining**          | Tasks expose `input_types` ➔ `output_types`; `Repository.build_pipelines()` connects everything that fits, end‑to‑end—from `source` to `sink`. |
| **Zero‑boilerplate Tasks**       | Sub‑class `Task`, implement `run()`, declare I/O types. That’s it.                                                                             |
| **Automatic pipeline discovery** | Provide a bag of Tasks, get **all** viable Pipelines (optionally limited by `max_depth`).                                                      |
| **Drop‑in caching**              | `CachedExecutor` memoises every Task by a stable hash of its inputs, so repeated runs are lightning‑fast.                                      |

---

## 📦 Installation

```bash
pip install pypekit
# or
pip install git+https://github.com/pypekit/pypekit.git
```

---

## 🛠 API reference

| Class            | Description                                                           |
| ---------------- | --------------------------------------------------------------------- |
| `Task`           | Abstract base; subclass and implement `run`.                          |
| `Pipeline`       | Internal ordered map of Tasks with `.run(input)` convenience.         |
| `Repository`     | Holds Tasks, enumerates Pipelines via `build_pipelines(max_depth=∞)`. |
| `CachedExecutor` | Executes many Pipelines with in‑memory cache (`.cache`, `.results`).  |

---

## ⚖️ License

Licensed under the **MIT License** — see [`LICENSE`](./LICENSE) for details.
