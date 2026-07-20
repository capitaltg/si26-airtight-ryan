**CONSTITUENCY**

_An AI practice simulator for governing under pressure_

Feature & Spec Sheet  ·  MVP Proposal  ·  July 1, 2026

A role-play simulator where users act as an elected representative fielding questions, complaints, and pushback from AI constituent personas, then get scored on clarity, persuasiveness, and whether they addressed or dodged the concern.

**1\. Overview**

*   **Setup**: The user plays an elected official or candidate, dropped into a town hall, one-on-one meeting, or hostile media interview.
    
*   **Personas**: AI-driven constituent personas, each with distinct demographics, values, and priorities, raise real concerns and push back in character.
    
*   **Loop**: The user responds in their own words; the app scores the exchange and reports how it shifted that persona's support.
    

**2\. Who It's For**

*   **Practitioners**: First-time or local candidates and campaign volunteers rehearsing town halls; advocacy and community organizers practicing persuasion across disagreement
    
*   **Education**: Civics and poli-sci classrooms, high school through college; debate programs; student government
    

**3\. Purpose**

*   **Learning**: Makes users feel the core tension of governing first-hand: every position pleases some constituents and alienates others; there is no answer that satisfies everyone
    
*   **Skills**: Builds thinking-on-your-feet, clear communication under pressure, and charitable engagement with opposing views, in a low-stakes, repeatable setting
    

**4\. Core Features**

*   **Grounded persona library**: Constituents with distinct demographics, values, and priorities (e.g. different views on political spectrum, retiree on fixed income, small-business owner, young renter, worried parent), each consistent in character across a session
    
    *   Preset personas built into the app, plus a documented reference set and Markdown template so teachers or campaign staff can author their own
        
*   **Scenario modes**: Town hall (many personas at once), one-on-one meeting, and hostile media interview, each with its own pacing and difficulty curve
    
*   **Performance scoring**: Structured feedback on clarity, persuasiveness, and responsiveness (did the user address the concern or dodge it), plus a per-persona support-shift readout with rationale
    

**Clarity**: structure, directness, jargon, and whether the response acknowledges the concern before answering

**Persuasiveness**: concrete evidence and specific commitments versus vague reassurance, tone matched to what the persona cares about

**Responsiveness**: checks each distinct sub-question raised and flags deflection or filler as a dodge, not just a binary "did they answer"

**Consistency check**: catches contradictions with something the user said earlier in the same session (useful in town hall mode, where one answer can undercut an earlier one)

**Support-shift readout**: a per-persona delta (e.g. -2 to +2) with a one-line rationale tied to the specific line that moved it, so it's not a black-box number

**Session scorecard**: rolls it all up at session's end and compares against prior sessions for the progress-tracking feature

*   **Adjustable difficulty**: Adjustable from friendly and curious to skeptical and adversarial, independent of scenario mode
    
*   **Conflicting-interests dashboard**: Live view showing how gaining one group's approval costs another's; the tradeoff made visible in real time
    
*   **Progress tracking**: Session history saved per user, so improvement in scoring trends is visible over time
    

**5\. Personas: Presets & Customization**

*   **Built-in library**: Built-in preset personas ship with the app and double as reference examples for how a well-specified persona should read
    
*   **Reference set**: A documented set of reference personas covering common archetypes across the political spectrum
    
*   **Markdown template**: A Markdown template lets teachers or campaign staff define new personas (demographics, values, priorities, tone, red lines) without touching code
    

**6\. MVP Scope**

*   **Approach**: Recommended phasing for a first release: enough to prove the core loop (converse, score, see tradeoffs) without building every planned feature up front.
    

**PHASE**

**FEATURE**

**NOTE**

**MVP**

**One-on-one meeting mode**

Simplest loop: single persona, single thread. Build and validate the core conversation and scoring engine here first

**MVP**

**5–6 built-in preset personas**

Enough variety to show contrast without a full authoring pipeline

**MVP**

**Core scoring: clarity, responsiveness, support shift**

The minimum feedback loop that makes the practice valuable

**MVP**

**Two difficulty levels (friendly / skeptical)**

Adversarial and media-hostile tones come later

**MVP**

**Basic session history (per user, local)**

Proves the progress-tracking value prop without a full dashboard

**V1.1**

**Town hall mode (multi-persona)**

Adds concurrency and cross-persona tradeoffs

**V1.1**

**Conflicting-interests dashboard**

Depends on multi-persona mode existing first

**V1.1**

**Markdown persona template + import**

Unlocks teacher/campaign customization

**V1.2**

**Hostile media interview mode**

Distinct rhythm (interruptions, gotcha framing); separate design pass

**V1.2**

**Classroom tools: assignments + grading review**

Needed for the education segment's institutional adoption, not for individual users

**Later**

**Full adversarial difficulty tier**

Highest design risk of feeling unfair rather than hard

**Later**

**Cross-session analytics for teachers/campaigns**

Aggregate reporting across many students or volunteers

**8\. Potential Data Sources for Persona Grounding**

*   **Pew Research Center, Political Typology**: Sorts the U.S. public into distinct value-based groups (nine as of the 2026 edition) using demographics, party lean, and issue positions; a strong reference for defining a persona's underlying values rather than just their party label.
    
*   **American National Election Studies (ANES)**: Long-running academic survey of voters' issue positions, party identification, and demographics tied to actual election cycles; useful for grounding how a persona would plausibly vote and why.
    
*   **General Social Survey (GSS), NORC**: Decades of tracked attitudes on social and political questions (trust in institutions, spending priorities, and more), useful for giving a persona historically consistent baseline views.
    
*   **Cooperative Election Study (CES)**: Large-sample survey with detailed policy opinions broken out by demographic and, in some releases, by congressional district; good for local-flavor personas.
    
*   **Gallup**: Ongoing topical polling on approval, party identification, and current issues; useful for keeping a persona's talking points current rather than static.
    
*   **U.S. Census Bureau, American Community Survey**: Income, age, housing costs, occupation, and education broken out down to the district level; useful for grounding a persona's economic situation and stated concerns in real local conditions.
    
*   **Bureau of Labor Statistics (BLS)**: Employment, wages, and industry data by region; useful for personas built around a specific occupation or local economic concern (for example, a small-business owner or a laid-off manufacturing worker).
    
*   **Ballotpedia**: District-level profiles, candidate positions, and ballot measure histories; useful for grounding a scenario in a specific, plausible district rather than a generic one.
    
*   **C-SPAN video library**: Real town hall footage, floor speeches, and constituent testimony; useful as style and rhythm reference for how real constituents phrase complaints and follow-up questions.
    
*   **Congress.gov hearing transcripts**: Committee hearing transcripts and public witness testimony; useful for modeling how a persona might structure a formal complaint or question in an interview-style scenario.
    
*   **Licensing and privacy note**: Confirm each source's terms of use before ingestion; favor public, aggregate statistics over individual-level or scraped data, and avoid attributing any generated persona statement to a real named person.
    

Additional ideas:

\- Background investigator (useful for recruiters who want to practice running background checks)
\- Feeding the AI transcription of actual politicians to create a persona