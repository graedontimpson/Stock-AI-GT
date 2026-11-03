# How the site works

How data becomes a prediction, where Claude (through Jev) comes in, and what
happens when a trade is placed. GitHub shows the diagram as a picture.

Jev is the only part that uses Claude. It explains predictions; it never
makes or changes them. The predictions come from a statistics model that runs
on the user's computer.

```mermaid
flowchart TD
    classDef source fill:#1f3a5f,stroke:#3987e5,color:#f0efec
    classDef step fill:#1a1a19,stroke:#5c5b56,color:#f0efec
    classDef ai fill:#4a2a1a,stroke:#d95926,color:#f0efec
    classDef claude fill:#3b2a4f,stroke:#9085e9,color:#f0efec
    classDef store fill:#163a2c,stroke:#199e70,color:#f0efec
    classDef user fill:#173a17,stroke:#0ca30c,color:#f0efec

    subgraph DAILY["Once a day: the first time the site opens, or scripts/daily_update.py"]
        direction TB
        W[("Wikipedia<br/>list of S&P 500 stocks")]:::source
        Y[("Yahoo Finance<br/>prices and volume")]:::source
        F[("FRED<br/>interest rates, inflation,<br/>unemployment, VIX")]:::source

        D["1. Download data<br/>10 years the first time, new days after"]:::step
        S["2. Signals<br/>15 numbers per stock per day:<br/>price trends, volume, market, economy"]:::step
        B["3. Backtest, weekly<br/>test on years the model hasn't seen<br/>→ track record vs always guessing 'rise'"]:::step
        M["4. Train the model<br/>logistic regression on ~1 million past days"]:::step
        P["5. Score every stock<br/>chance of rising in 3 months<br/>+ what pushed it up or down"]:::step
        G{"6. Has the method beaten<br/>guessing 'rise'?"}:::step
        SUG["Suggestion: Buy at 60%+, Sell at 40% or less,<br/>otherwise Hold; plus confidence and risk"]:::step
        HOLD["Every stock shows Hold<br/>(the case today: 57.4% vs 58.8%)"]:::step
        SC["7. Scorecard<br/>save today's Buy and Sell picks;<br/>grade the ones 3 months old"]:::step
        AT["8. AI trader<br/>buys at 60%+, ~5% of its account each;<br/>sells at 40% or less"]:::ai

        W & Y & F --> D --> S
        S --> B
        S --> M --> P
        B --> G
        P --> G
        G -- yes --> SUG
        G -- no --> HOLD
        SUG & HOLD --> SC
        P -- "probabilities only,<br/>ignores the 'beat guessing' rule" --> AT
    end

    subgraph SITE["On the website"]
        direction TB
        U(["You"]):::user
        PAGE["Stock page<br/>chart, suggestion, numbers"]:::step
        J["9. Jev<br/>sent only this stock's numbers;<br/>at most once per stock per day"]:::claude
        C[["Claude API"]]:::claude
        EX["Plain-English explanation:<br/>why · what stands out · what could make it wrong"]:::claude
        T["10. Place a trade<br/>latest Yahoo price → check cash or shares → record"]:::user

        U --> PAGE --> J --> C --> EX --> PAGE
        U --> T
    end

    subgraph DATA["Saved on your computer, in data/"]
        direction LR
        R[("results/<br/>daily scores")]:::store
        JV[("jev/<br/>explanations")]:::store
        A1[("account/<br/>your trades")]:::store
        A2[("ai_account/<br/>AI trades")]:::store
        SCF[("scorecard.csv")]:::store
    end

    SUG & HOLD --> R --> PAGE
    EX --> JV
    T --> A1
    AT --> A2
    SC --> SCF
```

## Key

| Color | Meaning |
| --- | --- |
| Blue | Free outside data sources |
| Gray | Steps that run on the user's computer |
| Orange | The AI trader, which trades by itself in its own account |
| Purple | Jev, the only part that uses Claude |
| Green | You, and what you do |
| Teal | Files saved in `data/` |
