# Chunking comparison: structural-v1 vs fixed size

Corpus: 42 documents. Fixed size: windows of 300 words, 15% overlap, no structure. Structural: sections, target 300 / max 400 / min 60 words (see README). Metrics are heuristics on the chunk text and are computed in the same way for both strategies.

| metric | structural-v1 | fixed 300 |
|---|---|---|
| chunks | 1669 | 1164 |
| size mean (words) | 180 | 296 |
| size median | 179 | 300 |
| size p95 | 298 | 300 |
| size max | 496 | 300 |
| start mid-sentence, % | 4.3 | 63.8 |
| end mid-sentence, % | 9.0 | 49.1 |
| spans >1 section, % | 23.1 | 60.5 |
| ends with a heading, % | 0.8 | 0.7 |
| chunks over 512 tokens (cut by the embedding model) | 2 | 124 |
| text beyond 512 tokens, % | 0.1 | 4.8 |

'Spans >1 section' is intended for the structural chunks (a tiny section is attached to its neighbour); for fixed chunks it shows how often a window mixes unrelated sections. 'Ends with a heading' is a string match: a line that repeats a heading text (for example a running header left in the text) is counted too.

## remote_work_policy

structural: 3 chunks (mean 86 words, mid-sentence start/end 0.0% / 0.0%); fixed: 1 chunks (mean 257, 0.0% / 0.0%).

Fixed chunk that cuts the text:

> Remote Work Policy 1. Purpose This policy explains who may work remotely, how remote days are approved and which security rules apply to com [...] eview The policy is reviewed once a year by HR and the information security officer. Questions about this policy go to hr@northwind.example.

Structural chunk with the same beginning (section: Remote Work Policy > 1. Purpose):

> Remote Work Policy 1. Purpose This policy explains who may work remotely, how remote days are approved and which security rules apply to com [...] patch roles are not eligible, because their work requires physical presence on site. Team leads may approve exceptions for a limited period.

## 2004_sprat

structural: 30 chunks (mean 224 words, mid-sentence start/end 3.3% / 23.3%); fixed: 26 chunks (mean 299, 69.2% / 80.8%).

Fixed chunk that cuts the text:

> the policies in which they are stated and are distinguished as either policy goals (strategic goals) or scenario goals (tactical goals) in e [...] ssions for each class of user. The included access levels are: a. Administrator b. Project Manager c. Analysts d. Guest  Goal Specification

Structural chunk with the same beginning (section: Security and Privacy Requirements Analysis Tool (SPRAT) Software Requirements Specification > 1. Introduction):

> All goals are fully traceable to the policies in which they are stated and are distinguished as either policy goals (strategic goals) or sce [...] ins a glossary of the terms used throughout this document. Additionally, it contains a bibliography of the references used in this document.

## 2004_grid_bgc

structural: 50 chunks (mean 116 words, mid-sentence start/end 0.0% / 20.0%); fixed: 23 chunks (mean 294, 47.8% / 52.2%).

Fixed chunk that cuts the text:

> TOC 2.6.2 Context sensitive online help manual 1. Each page will have a context sensitive link to the help system 2. Each context sensitive  [...] n account End users can apply for an account directly through the web portal. 1. Users must enter all required fields 2. The user must enter

Structural chunk with the same beginning (section: Software Requirements Specification > 2 Overall Description > 2.6 User Documentation > 2.6.1 Online Help Manual):

> 2.6 User Documentation 2.6.1 Online Help Manual 1. Full online manual 2. Major sections listed in TOC 2.6.2 Context sensitive online help ma [...] ll file based storage. 3 System Features 3.1 User Accounts Access to the functional areas of the system will be controlled by user accounts.

## 2006_eirene_sys_15

structural: 151 chunks (mean 191 words, mid-sentence start/end 1.3% / 13.2%); fixed: 111 chunks (mean 298, 58.6% / 51.4%).

Fixed chunk that cuts the text:

> CR 98-151.1 CR 98-152.1 (rev 1) CR 98-157.1 11.0 22 December 1998 CR 98-153.1 CR 98-154.2 CR 98-155.2 CR 98-156.2 CR 98-160.2 CR 98-161-1 CR [...] 010 (SCR 01-290.1) O-9011 (SCR 01-291.1) O-9012 (SCR 01-294.1) O-9013 (SCR 01-295.1) O-9014 (SCR 01-296.1) O-9015 (SCR 02-299.1) O-9016 (SCR

Structural chunk with the same beginning (section: UIC Project EIRENE System Requirements Specification > Document History):

> Document History Page 4 PSA167D006-15 Version Date Details 10.3 (cont) CR 98-144.1 CR 98-145.1 CR 98-146.1 CR 98-147.1 CR 98-148.1 CR 98-149 [...]  98-185-2 CR 98-186-1 CR 98-187-1 CR 98-188-1 CR 98-189-1 CR 98-190-1 CR 98-191-1 PSA167D006-15 Page 5 Document History Version Date Details

