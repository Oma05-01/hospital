import torch

# Make sure this path exactly matches what is in your inference.py!
checkpoint_path = 'checkpoints/medical_instruct_final_2.pt'

print("Loading checkpoint metadata...")
ckpt = torch.load(checkpoint_path, map_location='cpu')

print("\n--- BRAIN X-RAY RESULTS ---")
print(f"File Keys: {list(ckpt.keys())}")
print(f"Recorded Training Steps: {ckpt.get('step', 'NOT FOUND')}")
print(f"Final Loss: {ckpt.get('final_loss', 'NOT FOUND')}")
print("---------------------------\n")

import sys
from model import TransformerLM, create_causal_mask
from tokenizer3_4 import BPETokenizer
import torch.nn.functional as F

print("Booting Naked Brain...")
# 1. Load Model
model = TransformerLM(vocab_size=10000, d_model=512, n_layers=12, n_heads=8, d_ff=2048, max_seq_len=512)
model.load_state_dict(ckpt['model_state_dict'])
model.eval()  # CRITICAL: Turn off dropout

# 2. Load Tokenizer
tokenizer = BPETokenizer()
tokenizer.load('tokenizer_latest.json')  # Adjust path if needed

# 3. Format Prompt EXACTLY as trained
prompt = "QUESTION: What are the common symptoms of a migraine?\nANSWER: "
input_ids = torch.tensor([tokenizer.encode(prompt)], dtype=torch.long)

# 4. Generate with absolute zero creativity (Greedy Decoding)
print("Thinking...")
for _ in range(50):
    seq_len = input_ids.size(1)
    mask = create_causal_mask(seq_len)
    logits = model(input_ids, mask)

    # Take the absolute most likely next word
    next_token = torch.argmax(logits[:, -1, :], dim=-1).unsqueeze(0)
    input_ids = torch.cat([input_ids, next_token], dim=1)

print("\n--- FINAL RAW OUTPUT ---")
print(tokenizer.decode(input_ids[0].tolist()))
print("------------------------")