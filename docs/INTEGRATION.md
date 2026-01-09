# Integration patterns

ydst is deliberately independent of any particular layering/merge system.

The intended synergy pattern (whether you use DeepChainMap or any other deep-merge mechanism) is:

1. **Load** each YAML file into a template graph (ydst nodes are preserved).
2. **Layer/merge** the template graphs (treat ydst nodes as atomic leaves).
3. **Render once** at the end with runtime context and a registry.

This ensures that merge-time decisions happen on *templates*, not on already-evaluated concrete values.

## Why treat nodes as atomic

Template nodes are objects like `Var`, `Expr`, `ForEach`, etc. Most deep-merge systems should treat them as leaves:

- If a subtree is replaced by a node, the node should override the subtree.
- If a node is replaced by a subtree, the subtree should override the node.

Attempting to deep-merge “inside” a node is usually meaningless.

## Minimal example: layer then render

See `examples/07-layer-then-render.md` for a runnable sketch of this pattern without depending on any external merge library.

## Post-render validation

In production settings, it is often beneficial to validate the rendered output with a schema (Pydantic, JSON Schema, etc.). This keeps the templating layer simple and avoids mixing validation logic into templates.
