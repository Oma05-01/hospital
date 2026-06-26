"""
Transformer Language Model Implementation
All components built from scratch.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import math


def create_causal_mask(seq_len):
    """Create a causal mask for autoregressive attention."""
    mask = torch.tril(torch.ones(seq_len, seq_len)).bool()
    return mask


class TokenEmbedding(nn.Module):
    def __init__(self, vocab_size, d_model):
        """Token embedding layer."""
        super().__init__()
        self.embedding = nn.Parameter(torch.randn(vocab_size, d_model))
        self.d_model = d_model
    
    def forward(self, x):
        """
        Args:
            x: Token IDs, shape (batch_size, seq_len)
        Returns:
            Embeddings, shape (batch_size, seq_len, d_model)
        """
        return self.embedding[x] * (self.d_model ** 0.5)


class PositionalEncoding(nn.Module):
    def __init__(self, d_model, max_seq_len=5000):
        """Positional encoding using sine/cosine functions."""
        super().__init__()
        
        pe = torch.zeros(max_seq_len, d_model)
        position = torch.arange(0, max_seq_len).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2) * -(math.log(10000.0) / d_model))
        
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        
        self.register_buffer('pe', pe)
    
    def forward(self, x):
        """
        Args:
            x: Embeddings, shape (batch_size, seq_len, d_model)
        Returns:
            Embeddings + positional encoding
        """
        seq_len = x.size(1)
        return x + self.pe[:seq_len, :]


class MultiHeadAttention(nn.Module):
    def __init__(self, d_model, n_heads, dropout=0.1):
        """Multi-head self-attention."""
        super().__init__()
        assert d_model % n_heads == 0, "d_model must be divisible by n_heads"
        
        self.d_model = d_model
        self.n_heads = n_heads
        self.d_k = d_model // n_heads
        
        self.W_q = nn.Parameter(torch.randn(d_model, d_model))
        self.W_k = nn.Parameter(torch.randn(d_model, d_model))
        self.W_v = nn.Parameter(torch.randn(d_model, d_model))
        self.W_o = nn.Parameter(torch.randn(d_model, d_model))
        self.attn_dropout = nn.Dropout(dropout)
    
    def forward(self, x, mask=None):
        """
        Args:
            x: Input, shape (batch_size, seq_len, d_model)
            mask: Causal mask, shape (seq_len, seq_len)
        Returns:
            Attention output, shape (batch_size, seq_len, d_model)
        """
        batch_size = x.size(0)
        seq_len = x.size(1)
        
        # Create Q, K, V
        Q = x @ self.W_q
        K = x @ self.W_k
        V = x @ self.W_v
        
        # Split into multiple heads
        Q = Q.view(batch_size, seq_len, self.n_heads, self.d_k)
        K = K.view(batch_size, seq_len, self.n_heads, self.d_k)
        V = V.view(batch_size, seq_len, self.n_heads, self.d_k)
        
        # Transpose to (batch_size, n_heads, seq_len, d_k)
        Q = Q.transpose(1, 2)
        K = K.transpose(1, 2)
        V = V.transpose(1, 2)
        
        # Compute attention scores
        scores = Q @ K.transpose(-2, -1)
        scores = scores / math.sqrt(self.d_k)
        
        # Apply mask
        if mask is not None:
            mask = mask.unsqueeze(0).unsqueeze(0)
            scores = scores.masked_fill(~mask, float('-inf'))
        
        # Softmax
        attention_weights = F.softmax(scores, dim=-1)
        attention_weights = self.attn_dropout(attention_weights)
        
        # Apply attention to values
        output = attention_weights @ V
        
        # Concatenate heads
        output = output.transpose(1, 2)
        output = output.contiguous().view(batch_size, seq_len, self.d_model)
        
        # Final projection
        output = output @ self.W_o
        
        return output


class FeedForward(nn.Module):
    def __init__(self, d_model, d_ff, dropout=0.1):
        """Feed-forward network."""
        super().__init__()
        
        self.W_1 = nn.Parameter(torch.randn(d_model, d_ff))
        self.b_1 = nn.Parameter(torch.zeros(d_ff))
        
        self.W_2 = nn.Parameter(torch.randn(d_ff, d_model))
        self.b_2 = nn.Parameter(torch.zeros(d_model))
        
        self.dropout = dropout
    
    def forward(self, x):
        """
        Args:
            x: Input, shape (batch_size, seq_len, d_model)
        Returns:
            Output, shape (batch_size, seq_len, d_model)
        """
        hidden = x @ self.W_1 + self.b_1
        hidden = F.gelu(hidden)
        hidden = F.dropout(hidden, p=self.dropout, training=self.training)
        output = hidden @ self.W_2 + self.b_2
        return output


class LayerNorm(nn.Module):
    def __init__(self, d_model, eps=1e-6):
        """Layer normalization."""
        super().__init__()
        self.gamma = nn.Parameter(torch.ones(d_model))
        self.beta = nn.Parameter(torch.zeros(d_model))
        self.eps = eps
    
    def forward(self, x):
        """
        Args:
            x: Input, shape (batch_size, seq_len, d_model)
        Returns:
            Normalized output
        """
        mean = x.mean(dim=-1, keepdim=True)
        var = x.var(dim=-1, keepdim=True, unbiased=False)
        x_norm = (x - mean) / torch.sqrt(var + self.eps)
        return self.gamma * x_norm + self.beta


class TransformerBlock(nn.Module):
    def __init__(self, d_model, n_heads, d_ff, dropout=0.1):
        """Single transformer block."""
        super().__init__()
        
        self.attention = MultiHeadAttention(d_model, n_heads, dropout)
        self.feed_forward = FeedForward(d_model, d_ff, dropout)
        
        self.norm1 = LayerNorm(d_model)
        self.norm2 = LayerNorm(d_model)
        
        self.dropout = dropout
    
    def forward(self, x, mask=None):
        """
        Args:
            x: Input, shape (batch_size, seq_len, d_model)
            mask: Attention mask
        Returns:
            Output, shape (batch_size, seq_len, d_model)
        """
        # Attention with residual
        attn_output = self.attention(self.norm1(x), mask)
        attn_output = F.dropout(attn_output, p=self.dropout, training=self.training)
        x = x + attn_output
        
        # Feed-forward with residual
        ff_output = self.feed_forward(self.norm2(x))
        ff_output = F.dropout(ff_output, p=self.dropout, training=self.training)
        x = x + ff_output
        
        return x


class TransformerLM(nn.Module):
    def __init__(self, vocab_size, d_model=512, n_layers=6, n_heads=8,
                 d_ff=2048, max_seq_len=512, dropout=0.1):
        """
        Transformer Language Model.
        
        Args:
            vocab_size: Size of vocabulary
            d_model: Embedding dimension
            n_layers: Number of transformer blocks
            n_heads: Number of attention heads
            d_ff: Feed-forward hidden dimension
            max_seq_len: Maximum sequence length
            dropout: Dropout probability
        """
        super().__init__()
        
        self.d_model = d_model
        self.vocab_size = vocab_size
        
        # Embeddings
        self.token_embedding = TokenEmbedding(vocab_size, d_model)
        self.positional_encoding = PositionalEncoding(d_model, max_seq_len)
        
        # Transformer blocks
        self.blocks = nn.ModuleList([
            TransformerBlock(d_model, n_heads, d_ff, dropout)
            for _ in range(n_layers)
        ])
        
        # Final layer norm
        self.final_norm = LayerNorm(d_model)
        
        # Output projection
        self.output_projection = nn.Parameter(torch.randn(d_model, vocab_size))
        
        self.dropout = dropout
        
        # Initialize weights
        self._init_weights()
    
    def _init_weights(self):
        """Initialize weights with small random values."""
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_uniform_(p)
    
    def forward(self, x, mask=None):
        """
        Forward pass.
        
        Args:
            x: Token IDs, shape (batch_size, seq_len)
            mask: Attention mask, shape (seq_len, seq_len)
        Returns:
            Logits, shape (batch_size, seq_len, vocab_size)
        """
        # Embeddings
        x = self.token_embedding(x)
        x = self.positional_encoding(x)
        x = F.dropout(x, p=self.dropout, training=self.training)
        
        # Transformer blocks
        for block in self.blocks:
            x = block(x, mask)
        
        # Final norm and projection
        x = self.final_norm(x)
        logits = x @ self.output_projection
        
        return logits
    
    def generate(self, idx, max_new_tokens, temperature=1.0, top_k=None, top_p=None):
        """
        Generate new tokens autoregressively.
        
        Args:
            idx: Starting tokens, shape (batch_size, seq_len)
            max_new_tokens: Number of tokens to generate
            temperature: Sampling temperature
            top_k: Optional top-k filtering
        Returns:
            Generated tokens
        """
        for _ in range(max_new_tokens):
            idx_cond = idx if idx.size(1) <= self.positional_encoding.pe.size(0) else idx[:,
                                                                                      -self.positional_encoding.pe.size(
                                                                                          0):]
            seq_len = idx_cond.size(1)
            mask = create_causal_mask(seq_len).to(idx.device)
            logits = self.forward(idx_cond, mask)

            
            if top_k is not None:
                v, _ = torch.topk(logits, min(top_k, logits.size(-1)))
                logits[logits < v[:, [-1]]] = float('-inf')

            if top_p is not None:
                sorted_logits, sorted_idx = torch.sort(logits, descending=True)
                cum_probs = torch.cumsum(F.softmax(sorted_logits, dim=-1), dim=-1)
                remove = cum_probs - F.softmax(sorted_logits, dim=-1) > top_p
                sorted_logits[remove] = float('-inf')
                logits = torch.scatter(logits, 1, sorted_idx, sorted_logits)
            
            probs = F.softmax(logits, dim=-1)
            idx_next = torch.multinomial(probs, num_samples=1)
            idx = torch.cat([idx, idx_next], dim=1)
        
        return idx


if __name__ == "__main__":
    # Test the model
    print("Testing Transformer LM...")
    
    vocab_size = 1000
    batch_size = 2
    seq_len = 10
    
    model = TransformerLM(
        vocab_size=vocab_size,
        d_model=128,
        n_layers=2,
        n_heads=4,
        d_ff=512,
        max_seq_len=512
    )
    
    print(f"Model has {sum(p.numel() for p in model.parameters()):,} parameters")
    
    # Test forward pass
    x = torch.randint(0, vocab_size, (batch_size, seq_len))
    mask = create_causal_mask(seq_len)
    
    logits = model(x, mask)
    print(f"Input shape: {x.shape}")
    print(f"Output shape: {logits.shape}")
    
    # Test generation
    start_tokens = torch.randint(0, vocab_size, (1, 5))
    generated = model.generate(start_tokens, max_new_tokens=10)
    print(f"Generated shape: {generated.shape}")
    print("All tests passed!")
