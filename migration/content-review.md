# Content review: possible errors in the original site

Everything below appears **verbatim** on the new site. Nothing here has been silently corrected. A lab member should confirm each item before editing `src/data/*.json`.

## Hyperlinks that point to the wrong person (hidden on the new site, kept in the data)
| Person | Archived link | Problem | Evidence |
|---|---|---|---|
| Linjiang Wu | scholar `kiTENtllKw4C` | Same Scholar ID as Adedotun Akintayo; it is Akintayo's profile | `migration/people-web-search.json` (Wu's own: `UwkVywQAAAAJ`) |
| Zhisheng Zhang | `vn.linkedin.com/in/truong-tran-62643194` | Copy of Truong Tran's LinkedIn | same |

These are listed in `src/data/link-corrections.json`. Remove an entry there to show the link again.

## Dead or outdated archived links (still shown)
- Aditya Balu: `adityabalu.mystrikingly.com` returns 403. Current: https://adityabalu.github.io/ (shown as a "Current link").
- Kin Gwn Lore: `kglore.weebly.com` returns 404.
- Nitesh Subedi: link is just `http://iastate.edu/`, not a personal page.

## Typos (original spelling kept)
- Research: "Laboratory capabil**ti**es" (heading); "non-manufactur**bale**".
- Team: Ashutosh Kumar Nirala "Dec**en**ber 2025"; Bernard Lee Xian Yeow "pursue**ding**", "**cyper**-physical"; Abdulrahman Alnagar "Dep**a**rment"; Chao Liu "dyn**m**ics"; Truong Tran "embedded computer**sion** system"; Zhanhong Jiang "joined the lab since Fall 2014".
- PI funding: "D3AI: Data **drive** discoveries" (probably "data-driven"); "customable agriculture".
- Alloy Das: "B.E. Information Technology ,Burdwan University,2022" (spacing).
- Name spelling: the site says "Sambit **Gadhai**", but Scholar and publications use "Sambit **Ghadai**".

## Factual inconsistencies to confirm
- **Funding date:** the FACT grant ends "06/31/2022", but June has 30 days.
- **Funding layout:** the amount for "A multi-scale data assimilation framework…" ("($990,471, 3/1/2017 - 2/29/2020)") is in its own paragraph in the original. The new site joins it to its grant for display only.
- **Souradeep Chattopadhyay:** updated on the original site on 2026-10-03 (re-fetched). The first degree line now reads "PhD, Mechanical engi**e**ering Iowa State University, 2026" (typo, and no comma before the university). Earlier it read " Statistics, Iowa State University, 2024".
- **Jaydeep-Ravindra Rade:** lists "Ph.D. Electrical Engineering, Iowa State University, 2021", but the bio says he graduated in December 2020 and then worked as a Ph.D. student under other advisors. That 2021 line may be the M.S.
- **Aakanksha:** listed under "Department of Mechanical Engineering", but the bio says B.Tech in Computer Science.
- **Jesse Lane:** listed as Ph.D. Mechanical Engineering, but his personal site (jesselane.net) gives Human Computer Interaction.
- **Stray heading:** the Team & Contact page ends with an empty "Doctoral Students" heading. It is not reproduced because it has no content.
- **Lab capabilities:** the "Microway Whisperstation" lines repeat, and "16 x Intel Xeon … 32 GB" appears 4 times. These are probably separate machines, so they are kept.
- **PI bio:** says "more than 250 peer-reviewed publications". The publication list has 384 entries, which include preprints. Both numbers are kept.
- **Teaching:** says "(August 2014 to present)", but the latest course listed is from 2018.

## Statuses that web search suggests are out of date (not changed)
From `migration/people-web-search.json`, 2026-10-03:
- Adedotun Akintayo: now at Boeing (site says Intel).
- Chao Liu: Associate Professor at Tsinghua since Dec 2022 (site says Assistant Professor).
- Zhanhong Jiang: back at ISU TrAC.
- Sambuddha Ghosal: at Bayer (site says MIT postdoc).
- Venkatesh Chinde: at NREL.
- Hsin-Jung Yang: Scholar profile verified at Intel. He is still listed as a current Doctoral Student.

Pages that show historical roles carry an archival note saying they are reproduced as listed on 2026-10-03.
