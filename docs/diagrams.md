# MSB Framework Diagrams

This document contains detailed Mermaid diagrams illustrating the architecture, data flows, and relationships within the MSB Framework.

## Architecture Overview

```mermaid
graph TB
    subgraph "Client Layer"
        A[Application Code]
        B[API Calls]
    end

    subgraph "Mega Layer"
        C[Manipulator]
        D[Operation Registry]
        E[Request Processor]
    end

    subgraph "Super Layer"
        F[Super Classes]
        G[Project Classes]
        H[Operation Handlers]
    end

    subgraph "Base Layer"
        I[BaseEntity]
        J[BaseContainer]
        K[Type Validation]
    end

    subgraph "Utils Layer"
        L[Logging Setup]
        M[Validation Functions]
    end

    A --> C
    B --> C
    C --> D
    C --> E
    E --> F
    E --> G
    F --> H
    G --> H
    H --> I
    H --> J
    I --> K
    J --> K
    F --> L
    G --> L
    I --> L
    J --> L
    K --> M
```

## Class Hierarchy

```mermaid
classDiagram
    direction TB

    %% Abstract Base Classes
     ABCMeta <|-- EntityMeta : inherits
     EntityMeta <|-- BaseEntity : metaclass
     ABC <|-- BaseContainer : inherits
     ABC <|-- Super : inherits
     ABC <|-- Project : inherits
     ABC <|-- Manipulator : inherits

    %% Base Layer
    BaseEntity <|-- BaseContainer

    class BaseEntity {
        +name: str
        +isactive: bool
        +_fields: Dict[str, type]
        +set(params: Dict)
        +get(key: str)
        +to_dict()
        +from_dict(data)
        +activate()
        +deactivate()
        +has_attribute(key)
        +clone()
        +clear()
        +__getitem__(key)
        +__setitem__(key, value)
        +__contains__(key)
    }

    class BaseContainer {
        +_items: Dict[str, T]
        +add(item: T)
        +remove(name: str)
        +get(name: str)
        +get_all()
        +get_items()
        +get_active_items()
        +get_inactive_items()
        +get_by_value(conditions)
        +set_items(items)
        +activate_item(name)
        +deactivate_item(name)
        +activate_all()
        +deactivate_all()
        +drop_active()
        +drop_inactive()
        +has_item(name)
        +clear()
        +clone()
        +__getitem__(key)
        +__setitem__(key, value)
        +__contains__(key)
        +__len__()
        +__iter__()
    }

    %% Super Layer
    class Super {
        +_manipulator: Manipulator
        +_methods: Dict
        +execute(obj, attributes)
        +register_method()
    }

    class Project {
        +_items: BaseContainer
        +add_item(item)
        +get_item(name)
        +create_item()*
        +activate_all()
        +deactivate_all()
    }

    %% Mega Layer
    class Manipulator {
        +_operations: Dict
        +_registry: Dict
        +register_operation()
        +process_request()
        +get_methods_for_type()
    }

    %% Relationships
    Super --> Manipulator : uses
    Project --> BaseContainer : uses
    Manipulator --> Super : manages
    BaseContainer o-- BaseEntity : contains
```

## Data Flow: Request Processing

```mermaid
flowchart TD
    A[Client] --> B{Request Type}
    B -->|Single| C[process_single_request]
    B -->|Batch| D[process_batch_request]

    C --> E[Validate Request]
    D --> F[Split into Singles]

    F --> E
    E --> G{Operation Exists?}
    G -->|No| H[Return Error]
    G -->|Yes| I[Get Super Instance]

    I --> J[Validate Object]
    J --> K{Object Valid?}
    K -->|No| L[Return Error]
    K -->|Yes| M[Execute Operation]

    M --> N[Format Response]
    N --> O[Return Result]

    H --> O
    L --> O
```

## Method Resolution Flow

```mermaid
flowchart TD
    A[execute called] --> B{Method specified?}
    B -->|Yes| C[Try explicit method]
    B -->|No| D[Try prefixed method]

    C --> E{Method exists?}
    E -->|Yes| F[Execute method]
    E -->|No| D

    D --> G{Method exists?}
    G -->|Yes| F
    G -->|No| H[Try type-specific method]

    H --> I{Method exists?}
    I -->|Yes| F
    I -->|No| J[Try container method]

    J --> K{Method exists?}
    K -->|Yes| F
    K -->|No| L[Try default method]

    L --> M{Method exists?}
    M -->|Yes| F
    M -->|No| N[Raise ValueError]

    F --> O[Return result]
    N --> P[Return error]
```

## Serialization Flow

```mermaid
flowchart TD
    A[to_dict called] --> B{Use cache?}
    B -->|Yes| C{Cache valid?}
    B -->|No| D[Build dict]

    C -->|Yes| E[Return cached]
    C -->|No| D

    D --> F[Add type field]
    F --> G[Add name & isactive]
    G --> H[Process each field]

    H --> I{Field is entity?}
    I -->|Yes| J{Cyclic reference?}
    I -->|No| K[Add field value]

    J -->|Yes| L[Add '<cyclic reference>']
    J -->|No| M[Recurse to_dict]

    K --> H
    L --> H
    M --> H

    H --> N{More fields?}
    N -->|Yes| H
    N -->|No| O{Cache enabled?}
    O -->|Yes| P[Store in cache]
    O -->|No| Q[Return dict]

    P --> Q
    E --> Q
```

## Type Validation Flow

```mermaid
flowchart TD
    A[validate_type called] --> B{Value is None?}
    B -->|Yes| C[Allow None]
    B -->|No| D[Resolve expected type]

    D --> E{Is Union?}
    E -->|Yes| F[Test each union type]
    E -->|No| G{Is Dict?}

    F --> H{Type matches?}
    H -->|Yes| I[Validation passed]
    H -->|No| J{Next union type?}
    J -->|Yes| F
    J -->|No| K[Raise TypeError]

    G -->|Yes| L[Validate dict structure]
    G -->|No| M{Is List?}

    L --> N[Check keys & values]
    N --> O{Valid?}
    O -->|Yes| I
    O -->|No| K

    M -->|Yes| P[Validate list elements]
    M -->|No| Q[Check direct type]

    P --> R{All elements valid?}
    R -->|Yes| I
    R -->|No| K

    Q --> S{Type matches?}
    S -->|Yes| I
    S -->|No| K

    C --> I
    I --> T[Return]
    K --> U[Log error & raise]
```

## Container Operations

```mermaid
stateDiagram-v2
    [*] --> Empty
    Empty --> HasItems : add()
    HasItems --> HasItems : add()
    HasItems --> Empty : clear()
    HasItems --> HasItems : remove()
    HasItems --> HasItems : get()
    HasItems --> HasItems : set_item()

    note right of HasItems
        - Query operations
        - Bulk operations
        - Serialization
    end note

    note right of Empty
        - Ready for items
        - Can deserialize
    end note
```

## Project Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Created : __init__()
    Created --> ItemsAdded : add_item()
    ItemsAdded --> ItemsAdded : create_item()
    ItemsAdded --> ItemsModified : activate_item()
    ItemsModified --> ItemsModified : deactivate_item()
    ItemsModified --> Serialized : to_dict()
    Serialized --> Deserialized : from_dict()
    Deserialized --> ItemsAdded

    ItemsAdded --> Cleared : clear()
    ItemsModified --> Cleared : clear()
    Cleared --> [*]

    note right of Created
        - Name set
        - Container initialized
    end note

    note right of ItemsAdded
        - Items managed
        - Type validation
    end note

    note right of ItemsModified
        - State changes
        - Bulk operations
    end note
```

## Manipulator Workflow

```mermaid
sequenceDiagram
    participant C as Client
    participant M as Manipulator
    participant S as Super
    participant O as Object

    C->>M: process_request(request)
    M->>M: validate request
    M->>M: get operation handler
    M->>S: execute(obj, attributes)
    S->>S: resolve method
    S->>O: call method on object
    O-->>S: return result
    S-->>M: return response
    M-->>C: return formatted result
```

## Error Handling Flow

```mermaid
flowchart TD
    A[Operation] --> B{Exception raised?}
    B -->|No| C[Return success]
    B -->|Yes| D{Exception type}

    D -->|ValidationError| E[Log validation error]
    D -->|TypeError| F[Log type error]
    D -->|ValueError| G[Log value error]
    D -->|KeyError| H[Log key error]
    D -->|Other| I[Log unexpected error]

    E --> J[Format error response]
    F --> J
    G --> J
    H --> J
    I --> J

    J --> K[Return error dict]
    C --> L[Return success dict]

    K --> M[Response]
    L --> M
```

## Caching Strategy

```mermaid
flowchart TD
    A[Method called] --> B{Cache enabled?}
    B -->|No| C[Execute method]
    B -->|Yes| D{Cache hit?}

    D -->|Yes| E[Return cached result]
    D -->|No| C

    C --> F{Should cache?}
    F -->|Yes| G[Store in cache]
    F -->|No| H[Return result]

    G --> H
    E --> H

    H --> I[Check cache size]
    I --> J{Cache full?}
    J -->|Yes| K[Evict oldest]
    J -->|No| L[End]

    K --> L
```

## Module Dependencies

```mermaid
graph TD
    subgraph "msb_arch"
        subgraph "base"
            BE[baseentity.py]
            BC[basecontainer.py]
            BI[__init__.py]
        end

        subgraph "super"
            S[super.py]
            P[project.py]
            SI[__init__.py]
        end

        subgraph "mega"
            M[manipulator.py]
            MI[__init__.py]
        end

        subgraph "utils"
            L[logging_setup.py]
            V[validation.py]
            UI[__init__.py]
        end

        MAIN[__init__.py]
    end

    BE --> L
    BC --> BE
    BC --> L

    S --> L
    S --> BE
    S --> BC
    P --> BC
    P --> BE
    P --> V
    P --> L

    M --> L

    V --> L

    BI --> BE
    BI --> BC
    SI --> S
    SI --> P
    MI --> M
    UI --> L
    UI --> V

    MAIN --> BI
    MAIN --> SI
    MAIN --> MI
    MAIN --> UI
```