# GitHub toolbox — 10 dépôts étudiés (Codex / Claude Code)

**But :** réutiliser des méthodes utiles sans installer automatiquement des logiciels tiers. Lecture sélective pour les développeurs et les agents. Les nombres d'étoiles circulant dans des posts ne constituent pas une vérification technique.

| Dépôt officiel | Usage observé | My Vidéo (motiongen-ai) | TMX test isolé |
|---|---|---|---|
| [VoiceStudio](https://github.com/debpalash/VoiceStudio) | Voix locale, transcription, doublage et MCP | **Explorer** un adaptateur opt-in de doublage, seulement avec voix consenties | Sans rapport |
| [ppt-master](https://github.com/hugohe3/ppt-master) | PowerPoint éditable depuis des documents | **Étudier** le raisonnement document → scènes vidéo ; ne pas assimiler PPTX à MP4 | Sans rapport |
| [God's Eye View](https://github.com/bilawalsidhu/gods-eye-view) | Globe 3D / données publiques | Non prioritaire | Hors périmètre ; ne pas introduire de surveillance |
| [REA](https://github.com/morluto/rea) | Analyse de fonctionnement et reverse engineering | Référence conceptuelle **avec autorisations et limites juridiques**, jamais copie aveugle | Inutile en routine ; ne pas analyser des services sans droit |
| [diagram-design](https://github.com/cathrynlavery/diagram-design) | Diagrammes HTML/SVG documentaires | Utile pour expliquer la Timeline, export et facturation | Utile pour documenter les frontières de confiance des tests |
| [paperclip](https://github.com/paperclipai/paperclip) | Gestion d'équipes d'agents | Idée de suivi des tâches ; pas de serveur à ajouter | Surdimensionné pour ce dépôt de tests |
| [Matt Pocock skills](https://github.com/mattpocock/skills) | TDD, code review, architecture et tickets | **Adopter les principes** de bug reproduction, TDD, revue | **Adopter** test-first et revue des risques |
| [ECC](https://github.com/affaan-m/everything-claude-code) | Règles et automatisations pour agents code | **S'inspirer** des garde-fous et de la vérification | **S'inspirer** de la vérification et de la sécurité |
| [Karpathy skills](https://github.com/multica-ai/andrej-karpathy-skills) | Réduire les erreurs des agents en codant | **Appliquer** simplicité et modifications ciblées | **Appliquer** preuve avant affirmation |
| [claude-mem](https://github.com/thedotmack/claude-mem) | Historique et résumé des sessions d'agent | Préférer des notes de passage de relais versionnées | Préférer des notes de test versionnées ; aucun enregistrement de secrets |

## Décisions fermes

- **Aucun code, plugin MCP, script d'installation, pipeline d'agents ou modèle de voix tiers n'est installé** par ce document.
- VoiceStudio est sous **AGPL-3.0** ; ses modèles ont leurs propres licences. Ne pas intégrer ni distribuer sa base de code dans un SaaS commercial sans revue juridique. La voix d'un tiers requiert un consentement explicite ; aucune imitation trompeuse.
- ppt-master produit des présentations PowerPoint, **pas** une nouvelle implémentation du moteur Remotion ou de la facturation Base44.
- REA ne donne pas le droit de copier un produit ou de contourner protections et licences.
- Ne jamais enregistrer dans une mémoire d'agent des jetons, conversations privées, données clients ou clés de paiement.
- Les assistants Codex doivent lire `AGENTS.md` et le skill local adapté à leur tâche avant d'éditer. Modifier peu, tester ce qui change, fournir un bilan exact.

## Usage par tâche

**My Vidéo** : voix et sous-titres → audit de consentement, droits et coût ; import PDF/PPTX → extraction/planification avant rendu ; rendu → tests Timeline V1, lecture, export et compatibilité legacy. Lire aussi `.agents/skills/video-delivery/SKILL.md`.

**TMX** : ne pas confondre dépôt de tests avec application produit. Pour chaque changement d'infrastructure, garder les images épinglées, runner gratuit, secrets temporaires et sortie limitée ; lire `.agents/skills/smoke-safety/SKILL.md` et lancer `python3 ci/preflight.py`.

**Projets futurs** : évaluer l'intérêt, les licences et les tests d'un outil avant d'en faire une dépendance ; ne jamais installer les dix projets par défaut.
