# Profile proofreading + enrichment brief

Input: migration/profiles/input-<chunk>.json. Each record has the person's original lab-site text (`lines`, in order),
original links, links already shown, and earlier web-search evidence (`webSearchEvidence`, `githubFinding`).

For EACH person produce one clean, well-organized, proofread profile for the SCSLab People/Alumni page.

## Rules
1. **Proofread** the original text: fix spelling, grammar, punctuation, capitalization, spacing, degree formatting
   (use "Ph.D.", "M.S.", "B.S.", "B.E.", "B.Tech.", "M.Tech."), awkward phrasing. Keep it third person, natural, concise,
   professional. Keep the person's facts and personal touches (hobbies are fine). Do not exaggerate.
2. **Enrich only from the person's OWN website / profile** (personal site, github.io, faculty page, own GitHub README,
   own Google Scholar header) that the evidence already ties to them (high confidence), or that you newly verify with
   concrete evidence (Iowa State / SCSLab / Sarkar / matching degree). Use WebFetch on those URLs. Do NOT fetch LinkedIn.
   Useful additions: current position (esp. alumni), degree completed since, research interests, notable focus.
   Every added or changed FACT needs an entry in `sources`. If nothing verifiable is found, just proofread.
3. Never invent facts, dates, employers, or degrees. If the original and the person's site conflict, prefer the person's
   own site for their *current* role, keep the lab-era facts, and note the conflict in `notes`.
4. Alumni: write lab-era facts in past tense ("joined the lab in Fall 2016", "worked on ..."). Put the present role in
   `currentPosition` only if verified (from the original text or own site), e.g. "Research Scientist, GE Vernova".
5. Education: one string per degree, newest first, format "Ph.D., Mechanical Engineering, Iowa State University, 2021".
   Keep unknown parts out rather than guessing.
6. Do not include email addresses in the bio. Keep `emailAsListed` handling to the site (not your job).

## Output: migration/profiles/out-<chunk>.json — JSON array, same order as input, one object per person:
{
 "name": "proofread display name (fix obvious misspellings only if the person's own site confirms, else unchanged)",
 "headline": "short role line, e.g. 'Ph.D. Student, Mechanical Engineering' or 'Ph.D. 2021 · now Research Scientist, GE Vernova'",
 "education": ["..."],
 "affiliation": ["Department of Mechanical Engineering, Iowa State University"]   // optional, non-degree affiliation lines
 "bio": ["paragraph", "..."],               // 1–2 paragraphs, proofread
 "researchInterests": "comma-separated short phrase or null",
 "joined": "Fall 2021 | null",
 "currentPosition": "string | null",
 "project": "string | null",               // e.g. undergrad project titles from the original
 "sources": [{"fact": "...", "url": "..."}],
 "changes": [{"original": "...", "edited": "...", "reason": "typo|grammar|format|updated from own site|..."}],
 "notes": "conflicts / anything a human should check"
}
Write only your out-<chunk>.json file. Final reply: counts of people enriched from own sites, and any conflicts.
