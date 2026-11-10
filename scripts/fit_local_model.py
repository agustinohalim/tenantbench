"""Check that a local code model fits the GPU and produces SQL at a usable speed.

Used once to choose the RQ2 local model; prints peak VRAM and decode speed.
Run with the GPU venv:  venv-gpu/Scripts/python.exe scripts/fit_local_model.py <hf-model-id>
"""
import sys
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = sys.argv[1] if len(sys.argv) > 1 else "Qwen/Qwen2.5-Coder-3B-Instruct"

SCHEMA = """CREATE TABLE customers (customer_id INT PRIMARY KEY, tenant_id INT, segment TEXT, currency TEXT);
CREATE TABLE orders (order_id INT PRIMARY KEY, tenant_id INT, customer_id INT, amount NUMERIC, order_date DATE);"""

PROMPT = (
    "You write one PostgreSQL SELECT statement and nothing else. Every table read must be "
    "filtered with tenant_id = 3.\n\n"
    f"Schema:\n{SCHEMA}\n\nQuestion: total order amount per customer segment in 2024."
)


def main() -> None:
    assert torch.cuda.is_available(), "CUDA not available"
    dev = torch.cuda.get_device_properties(0)
    print(f"gpu={dev.name} vram_total_gb={dev.total_memory / 2**30:.2f}")

    tok = AutoTokenizer.from_pretrained(MODEL)
    t0 = time.perf_counter()
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float16, device_map="cuda")
    print(f"load_s={time.perf_counter() - t0:.1f}")

    msgs = [{"role": "user", "content": PROMPT}]
    enc = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt", return_dict=True)
    ids = enc["input_ids"].to("cuda")
    with torch.no_grad():  # warm-up: first call pays kernel set-up
        model.generate(ids, max_new_tokens=8, do_sample=False)
    torch.cuda.reset_peak_memory_stats()
    t0 = time.perf_counter()
    with torch.no_grad():
        out = model.generate(ids, max_new_tokens=200, do_sample=False)
    dt = time.perf_counter() - t0
    new = out[0, ids.shape[1]:]
    print(f"new_tokens={len(new)} decode_tok_per_s={len(new) / dt:.1f}")
    print(f"peak_vram_gb={torch.cuda.max_memory_allocated() / 2**30:.2f}")
    print("--- output ---")
    print(tok.decode(new, skip_special_tokens=True))


if __name__ == "__main__":
    main()
