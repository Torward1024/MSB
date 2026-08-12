# Diagrams

The mechanisms, drawn. Prose for each is in [architecture.md](architecture.md).

## The layers

```mermaid
graph TB
    subgraph Caller
        A["script, window, CLI, server"]
    end

    subgraph Mega
        M["Manipulator"]
        R["operation registry"]
        P["pipeline"]
        I["interceptor chain"]
    end

    subgraph Super
        S["Super"]
        B["built-ins: inspect, configure,<br/>catalogue, save, load"]
        J["Project"]
    end

    subgraph Base
        E["BaseEntity"]
        C["BaseContainer[T]"]
        Z["Serializable"]
    end

    A -->|request as data| M
    M --> R
    M --> P
    P -->|one request per step| M
    M --> I
    I --> S
    S --- B
    S -->|applies methods to| E
    S -->|applies methods to| C
    J --> C
    E --> Z
    C --> Z
```

The Super layer never points upward: it needs one method from whatever drives it, declared as the
`MethodProvider` protocol.

## Class hierarchy

```mermaid
classDiagram
    direction TB

    class Serializable {
        +name: str
        +isactive: bool
        +revision: int
        +to_dict()
        +from_dict(data)
        +fingerprint()
        +clone()
    }

    class BaseEntity {
        +get(key)
        +set(params)
        +has_attribute(key)
        +clear()
    }

    class BaseContainer~T~ {
        +add(item)
        +remove(name)
        +get(name)
        +get_all()
        +get_by_value(criteria)
    }

    class Super {
        +OPERATION: str
        +execute(obj, attributes, method)
        #_apply_methods(obj, attributes)
        #_build_response(...)
    }

    class Manipulator {
        +process_request(request)
        +batch(requests)
        +pipeline(plan)
        +register_operation(super)
        +describe_operations()
        +describe_model()
    }

    class Project {
        +create_item()
        +add_item(item)
        +get_items()
    }

    Serializable <|-- BaseEntity
    Serializable <|-- BaseContainer
    Super <|-- Inspector
    Super <|-- Configurator
    Super <|-- Catalogue
    Super <|-- Persistence
    Super <|-- Loader
    Manipulator o-- Super : registers
    Project o-- BaseContainer : holds
```

`BaseEntity` and `BaseContainer` are siblings: `get`, `set` and `clear` mean different things to
each.

## One request

```mermaid
sequenceDiagram
    participant Caller
    participant M as Manipulator
    participant I as Interceptors
    participant S as Super
    participant O as Object

    Caller->>M: inspect(obj, get_price=None)
    M->>M: build the request
    M->>I: process_request
    I->>I: outermost first
    I->>S: execute(obj, attributes)
    S->>S: resolve a handler
    S->>O: apply each method named
    O-->>S: values
    S-->>I: response
    I-->>M: response
    M-->>Caller: unwrapped result
```

An interceptor may return a response without calling the next one, which is what refusing looks
like.

## Choosing a handler

```mermaid
flowchart TD
    A["request names a method"] --> B{"is it already<br/>a handler?"}
    B -->|yes| Z["run it"]
    B -->|no| C{"_operation_name<br/>exists?"}
    C -->|yes| Z
    C -->|no| D{"_operation_type<br/>exists?"}
    D -->|yes| Z
    D -->|no| E{"container, and<br/>_operation_basecontainer?"}
    E -->|yes| Z
    E -->|no| F{"_operation<br/>exists?"}
    F -->|yes| Z
    F -->|no| G["DispatchError"]
```

Only handlers of the operation are reachable. A name outside it falls through to a more general
handler rather than being called.

## A pipeline

```mermaid
flowchart TD
    subgraph Plan["plan, as data"]
        P1["written: save"]
        P2["read: load, after written"]
        P3["left: stats"]
        P4["right: audit"]
        P5["report: combine, obj @left, of @right"]
    end

    P1 --> S1
    P2 --> S2
    P3 --> S2
    P4 --> S2
    P5 --> S3

    subgraph Stages["stages, derived from the edges"]
        S1["stage 1: written"]
        S2["stage 2: read, left, right"]
        S3["stage 3: report"]
    end

    S1 --> S2 --> S3
```

Steps in one stage wait for nothing outside the stages before it, so they may run together.
Every step is still one `process_request`.

When a step fails, the branch below it is skipped and the rest still runs:

```mermaid
flowchart LR
    A["load: fails"] -->|skipped| B["inspect @load"]
    A -.->|unaffected| C["stats: runs"]
```

## Serialization

```mermaid
flowchart TD
    A["object"] --> B{"caching on and<br/>cache valid?"}
    B -->|yes| C["the cached mapping"]
    B -->|no| D["walk the written fields"]
    D --> E{"value is..."}
    E -->|"number, string, bool, None"| F["as it is"]
    E -->|"Serializable"| G{"already seen?"}
    G -->|yes| H["CYCLIC_REFERENCE"]
    G -->|no| I["to_dict, recursively"]
    E -->|"list, dict, set, tuple"| J["walk it"]
    F --> K["plain data with 'type'"]
    H --> K
    I --> K
    J --> K
```

Restoring reverses it, guided by the annotation: the declared type is what says a list was a
tuple or a set.

## Validating a value

```mermaid
flowchart TD
    A["value assigned"] --> B{"None?"}
    B -->|yes, and not 'name'| Z["accepted"]
    B -->|no| C{"a compiled check<br/>for this annotation?"}
    C -->|"yes, and it says yes"| Z
    C -->|"no, or it says no"| D["structural walk"]
    D --> E{"matches?"}
    E -->|yes| F["constraints on the annotation"]
    E -->|no| G["TypeValidationError,<br/>naming the element"]
    F -->|pass| Z
    F -->|fail| H["ConstraintError"]
```

The compiled check is a fast path for the shapes most models are made of. A refusal always goes
through the walk, so the message names what failed.

## Invalidating a cache

```mermaid
flowchart BT
    A["item.price = 9.0"] --> B["item's cache dropped"]
    B --> C["every owner's cache dropped"]
    C --> D["their owners, and so on"]
```

Invalidation walks up the ownership graph, because a container serialises its items. Ownership is
recorded when an object is assigned to a field or added to a container, and owners are held
weakly.

## What the orchestrator derives

```mermaid
flowchart LR
    A["registered Supers"] -->|"read source"| B["handlers, and the calls between them"]
    B --> C["describe_operations()"]
    B --> D["order_handlers()"]
    E["annotations"] -->|"read hints"| F["which type holds which"]
    F --> G["describe_model()"]
    F --> H["dependents_of()"]
    F --> I["scaffold()"]
```

Nothing here is written down twice, so a menu or a diagram built from it cannot go stale.

## A project

```mermaid
stateDiagram-v2
    [*] --> Empty: Project(name=...)
    Empty --> Holding: create_item() / add_item()
    Holding --> Holding: activate, deactivate, remove
    Holding --> Empty: clear()
    Holding --> Stored: to_dict()
    Stored --> Holding: from_dict()
    Holding --> [*]
```
