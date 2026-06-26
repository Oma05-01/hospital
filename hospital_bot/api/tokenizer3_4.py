"""
BPE Tokenizer Implementation
"""
import regex as re
import json


class BPETokenizer:
    def __init__(self, vocab_size=10000):
        self.vocab_size = vocab_size
        self.merges = {}
        self.vocab = {}
        self.special_tokens = {}
        
        # GPT-style regex pattern for pre-tokenization
        self.pattern = re.compile("|".join([
            r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
            r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
            r"""\p{N}{1,3}""",
            r""" ?[^\s\p{L}\p{N}]+[\r\n/]*""",
            r"""\s*[\r\n]+""",
            r"""\s+(?!\S)""",
            r"""\s+""",
        ]))
    
    def train(self, text):
        """Train the BPE tokenizer on the given text."""
        print("Starting BPE training...")
        
        # Split text using regex pattern
        text_chunks = re.findall(self.pattern, text)
        
        # Convert all chunks to UTF-8 bytes and flatten
        tokens = []
        for chunk in text_chunks:
            chunk_bytes = chunk.encode("utf-8")
            tokens.extend(list(chunk_bytes))
        
        print(f"Total tokens before training: {len(tokens):,}")
        
        # BPE training loop
        num_merges = self.vocab_size - 256
        ids = list(tokens)
        
        for i in range(num_merges):
            stats = self._get_stats(ids)
            if not stats:
                print(f"No more pairs to merge at iteration {i}")
                break
                
            pair = max(stats, key=stats.get)
            idx = 256 + i
            
            if (i + 1) % 100 == 0:
                print(f"Merge {i+1}/{num_merges}: {pair} -> {idx}")
            
            ids = self._merge(ids, pair, idx)
            self.merges[pair] = idx
        
        print(f"Total tokens after training: {len(ids):,}")
        print(f"Compression ratio: {len(tokens) / len(ids):.2f}X")
        
        # Build vocab
        self.vocab = {idx: bytes([idx]) for idx in range(256)}
        for (p0, p1), idx in self.merges.items():
            self.vocab[idx] = self.vocab[p0] + self.vocab[p1]
        
        print(f"Vocabulary built with {len(self.vocab)} tokens")
    
    def encode(self, text):
        """Encode text into token IDs."""
        # Split text into chunks using regex
        text_chunks = re.findall(self.pattern, text)
        
        ids = []
        for chunk in text_chunks:
            # Convert chunk to UTF-8 bytes
            chunk_bytes = list(chunk.encode("utf-8"))
            
            # Apply BPE merges greedily
            while True:
                stats = self._get_stats(chunk_bytes)
                if not stats:
                    break
                
                # Find the pair that was merged earliest in training
                pair = min(stats, key=lambda p: self.merges.get(p, float("inf")))
                if pair not in self.merges:
                    break
                
                idx = self.merges[pair]
                chunk_bytes = self._merge(chunk_bytes, pair, idx)
            
            ids.extend(chunk_bytes)
        
        return ids
    
    def decode(self, ids):
        """Decode token IDs back into text."""
        byte_tokens = b"".join(self.vocab[idx] for idx in ids)
        text = byte_tokens.decode("utf-8", errors="replace")
        return text
    
    def save(self, filepath):
        """Save tokenizer to a file."""
        data = {
            "vocab_size": self.vocab_size,
            "merges": {str(k): v for k, v in self.merges.items()},
            "vocab": {k: list(v) for k, v in self.vocab.items()},
            "special_tokens": self.special_tokens
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f)
        
        print(f"Tokenizer saved to {filepath}")
    
    def load(self, filepath):
        """Load tokenizer from a file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        self.vocab_size = data["vocab_size"]
        self.special_tokens = data["special_tokens"]
        
        # Reconstruct merges with tuple keys
        self.merges = {}
        for key_str, value in data["merges"].items():
            p0, p1 = key_str.strip("()").split(", ")
            key_tuple = (int(p0), int(p1))
            self.merges[key_tuple] = value
        
        # Reconstruct vocab with bytes values
        self.vocab = {}
        for key, value_list in data["vocab"].items():
            self.vocab[int(key)] = bytes(value_list)
        
        print(f"Tokenizer loaded from {filepath}")
    
    def register_special_tokens(self, special_tokens):
        """Register special tokens like <|endoftext|>."""
        self.special_tokens = special_tokens
        
        for token_str, token_id in special_tokens.items():
            self.vocab[token_id] = token_str.encode("utf-8")
        
        print(f"Registered {len(special_tokens)} special tokens")
    
    def _get_stats(self, ids):
        """Count frequency of all adjacent pairs."""
        counts = {}
        for pair in zip(ids, ids[1:]):
            counts[pair] = counts.get(pair, 0) + 1
        return counts
    
    def _merge(self, ids, pair, idx):
        """Replace all occurrences of pair with idx."""
        newids = []
        i = 0
        while i < len(ids):
            if i < len(ids) - 1 and ids[i] == pair[0] and ids[i + 1] == pair[1]:
                newids.append(idx)
                i += 2
            else:
                newids.append(ids[i])
                i += 1
        return newids


if __name__ == "__main__":
    # Test the tokenizer
    tokenizer = BPETokenizer(vocab_size=500)

    with open('data/train.txt', 'r', encoding='utf-8') as f:
        test_text = f.read(10_000_000)  # 10 million chars

    print(f"Loaded {len(test_text):,} characters for tokenizer training")
    
    print("Training tokenizer...")
    tokenizer.train(test_text)
    
    print("\nTesting encode/decode...")
    test_str = "Hello world! Testing the tokenizer."
    encoded = tokenizer.encode(test_str)
    decoded = tokenizer.decode(encoded)
    
    print(f"Original: {test_str}")
    print(f"Encoded: {encoded}")
    print(f"Decoded: {decoded}")
    print(f"Match: {test_str == decoded}")
    
    print("\nSaving tokenizer...")
    tokenizer.save("test_tokenizer.json")
    
    print("\nLoading tokenizer...")
    tokenizer2 = BPETokenizer()
    tokenizer2.load("test_tokenizer.json")
    
    encoded2 = tokenizer2.encode(test_str)
    print(f"Encoded with loaded tokenizer: {encoded2}")
    print(f"Match: {encoded == encoded2}")
