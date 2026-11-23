"""
Phrases shown in the mascot's bubble, in French and English (no Qt here).

Categories
    mascot     lines in the mascot's own voice (lively, funny, a bit theatrical)
    quote      studio / creation maxims (original, no attribution)
    tip        the mastering teacher: loudness, true peak, dynamics, headroom,
               gain staging, references, A/B listening, Anti-Parasite, exports
    action     while a batch is running
    listen     when audio playback starts
    hatch, grow, grow_max, batch_done, batch_failed, batch_cancelled
               reactions to events

To add a phrase: append a tuple (id, category, French, English) here, and its
other languages in phrases_world.py (same id). A missing language shows the
English text instead. Keep phrases under ~120 characters so they fit the bubble.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from . import N_
from .fr import _french_spacing
from .phrases_world import PHRASE_TRANSLATIONS

_DATA: Sequence[tuple] = (
    # ---- the mascot's voice --------------------------------------------------
    ("m.hello", "mascot", "Coucou ! Je surveille tes niveaux, promis je ne touche à rien.",
     "Hi! I'm watching your levels. I promise I won't touch a thing."),
    ("m.helmet", "mascot", "Encore quelques batchs et il me faudra un plus grand casque.",
     "A few more batches and I'll need bigger headphones."),
    ("m.pitch", "mascot", "J'ai l'oreille absolue. Enfin… presque.", "I have perfect pitch. Well… almost."),
    ("m.together", "mascot", "Tu m'as fait éclore, maintenant on finit ce morceau ensemble !",
     "You hatched me, now let's finish this track together!"),
    ("m.lufs", "mascot", "Moi, je suis réglé à -14 LUFS en permanence.", "Me? I'm permanently set to -14 LUFS."),
    ("m.gainmatch", "mascot", "Psst… le bouton Gain Match, c'est mon préféré.",
     "Psst… the Gain Match button is my favourite."),
    ("m.dance", "mascot", "Je danse mieux quand tu masterises.", "I dance better when you're mastering."),
    ("m.click", "mascot", "Clique sur moi et je te sors une autre phrase.",
     "Click me and I'll come up with another line."),
    ("m.float", "mascot", "Je ne dors jamais. Je flotte.", "I never sleep. I float."),
    ("m.feel", "mascot", "Ton prochain son va tout casser, je le sens dans mes circuits.",
     "Your next track is going to smash it, I can feel it in my circuits."),
    ("m.count", "mascot", "Je compte tes batchs : chacun me fait grandir !",
     "I'm counting your batches: every one makes me grow!"),
    ("m.coffee", "mascot", "Un petit café, un grand master ?", "A small coffee, a big master?"),
    ("m.peak", "mascot", "Je suis petit, mais mon true peak est sous contrôle.",
     "I'm small, but my true peak is under control."),
    ("m.release", "mascot", "Allez, on lâche ce morceau dans le monde !", "Come on, let's release this track into the world!"),
    ("m.clean", "mascot", "Pas de parasites ici, j'ai fait le ménage.", "No parasites in here, I've tidied up."),
    ("m.ears", "mascot", "Je n'ai pas d'oreilles, mais j'écoute très bien.", "I don't have ears, but I listen very well."),
    ("m.drop", "mascot", "Préviens-moi avant le drop, que je m'accroche.", "Warn me before the drop so I can hold on."),
    ("m.loop", "mascot", "Cette boucle tourne dans ma tête depuis tout à l'heure.",
     "That loop has been stuck in my head for a while now."),

    # ---- studio / creation maxims (original) -------------------------------
    ("q.silence", "quote", "Le silence fait partie du morceau.", "Silence is part of the track."),
    ("q.finish", "quote", "Termine le morceau. La perfection viendra au suivant.",
     "Finish the track. Perfection can wait for the next one."),
    ("q.arrangement", "quote", "Un bon mix commence par un bon arrangement.", "A good mix starts with a good arrangement."),
    ("q.morning", "quote", "L'oreille fraîche du matin a souvent raison.", "Fresh morning ears are usually right."),
    ("q.fewer", "quote", "Moins de pistes, plus d'émotion.", "Fewer tracks, more emotion."),
    ("q.take", "quote", "Le meilleur plugin, c'est une bonne prise.", "The best plugin is a good take."),
    ("q.finished", "quote", "Un morceau fini t'apprend plus que dix morceaux commencés.",
     "One finished track teaches you more than ten started ones."),
    ("q.groove", "quote", "Le groove pardonne beaucoup d'erreurs.", "Groove forgives a lot of mistakes."),
    ("q.contrast", "quote", "Sans moment calme, le drop ne frappe pas.", "Without a quiet moment, the drop doesn't hit."),
    ("q.create", "quote", "Crée d'abord, juge ensuite.", "Create first, judge later."),
    ("q.reference", "quote", "La référence guide, ton oreille décide.", "The reference guides, your ears decide."),
    ("q.simple", "quote", "Une idée simple bien finie bat une idée géniale jamais terminée.",
     "A simple idea, well finished, beats a brilliant one never completed."),
    ("q.save", "quote", "Sauvegarde. Puis sauvegarde encore.", "Save. Then save again."),
    ("q.emotion", "quote", "La musique, c'est de l'émotion avec un tempo.", "Music is emotion with a tempo."),

    # ---- mixing / mastering knowledge + app tips ---------------------------
    ("t.ceiling", "tip", "Garde un plafond à -1 dBTP pour le MP3 / AAC : l'encodage peut créer des pics.",
     "Keep the ceiling at -1 dBTP for MP3 / AAC: encoding can create new peaks."),
    ("t.streaming", "tip", "Les plateformes baissent les masters trop forts (vers -14 à -16 LUFS) : plus fort n'est pas plus fort.",
     "Streaming platforms turn loud masters down (to about -14 to -16 LUFS): louder isn't louder."),
    ("t.gainmatch", "tip", "Compare toujours à volume égal (Gain Match) : sinon le plus fort gagne à l'oreille.",
     "Always compare at equal loudness (Gain Match): otherwise the louder one wins by ear."),
    ("t.refgenre", "tip", "Choisis une référence du même genre : la correspondance tonale sera bien plus juste.",
     "Pick a reference in the same genre: the tonal match will be far more accurate."),
    ("t.headroom", "tip", "Avant le mastering, laisse de la marge au mix : des pics vers -6 à -3 dBFS.",
     "Before mastering, leave headroom in the mix: peaks around -6 to -3 dBFS."),
    ("t.camelot", "tip", "Camelot : 8A s'enchaîne avec 7A, 9A et 8B pour un mix harmonique.",
     "Camelot: 8A blends with 7A, 9A and 8B for harmonic mixing."),
    ("t.camelot2", "tip", "Camelot : même numéro, lettre différente = relatives majeure et mineure.",
     "Camelot: same number, other letter = relative major and minor."),
    ("t.double", "tip", "BPM détecté à 87 au lieu de 174 ? Les boutons ÷2 / ×2 de la carte sont là pour ça.",
     "BPM detected as 87 instead of 174? The card's ÷2 / ×2 buttons are made for that."),
    ("t.bits", "tip", "Garde un WAV 24 bits comme master : le 16 bits (avec dither) sert au CD.",
     "Keep a 24-bit WAV as your master: 16-bit (with dither) is for CD."),
    ("t.sub", "tip", "Les infra-basses inaudibles mangent la marge du limiteur : nettoie-les dans le mix.",
     "Inaudible sub-bass eats the limiter's headroom: clean it up in the mix."),
    ("t.systems", "tip", "Écoute ton master partout : casque, voiture, téléphone.",
     "Check your master everywhere: headphones, car, phone."),
    ("t.mono", "tip", "Vérifie en mono : la basse et la voix doivent rester solides.",
     "Check in mono: the bass and the vocal should stay solid."),
    ("t.truepeak", "tip", "Le true peak mesure les pics entre les échantillons : c'est lui qui évite la saturation à l'encodage.",
     "True peak measures peaks between samples: it's what prevents clipping after encoding."),
    ("t.lufs", "tip", "Les LUFS intégrés mesurent le volume perçu sur tout le morceau, pas les pics.",
     "Integrated LUFS measure perceived loudness over the whole track, not the peaks."),
    ("t.limiter", "tip", "Un limiteur qui réduit de plus de 4 à 6 dB écrase souvent les transitoires.",
     "A limiter reducing more than 4 to 6 dB often flattens the transients."),
    ("t.clip", "tip", "Le clip social démarre sur un temps quand le BPM est connu : vérifie-le avant d'exporter.",
     "The social clip starts on a beat when the BPM is known: check it before exporting."),
    ("t.pack", "tip", "Pack de sortie = WAV 24 bits + MP3 320 tagué + pochette, rangés dans un dossier.",
     "Release pack = 24-bit WAV + tagged MP3 320 + cover, in one folder."),
    ("t.trim", "tip", "L'auto-trim garde 10 ms avant le premier son : l'attaque reste intacte.",
     "Auto-trim keeps 10 ms before the first sound: the attack stays intact."),
    ("t.cover", "tip", "Les pochettes sont recadrées en carré : centre ton visuel principal.",
     "Covers are cropped to a square: keep your main visual centred."),
    ("t.breaks", "tip", "Fais des pauses : la fatigue auditive fausse le jugement des aigus.",
     "Take breaks: ear fatigue skews how you judge the highs."),
    ("t.volume", "tip", "Mixe à volume modéré : l'équilibre grave / aigu est plus fiable.",
     "Mix at a moderate volume: the bass / treble balance is more reliable."),
    ("t.deesser", "tip", "Trop de sifflantes ? Un de-esser sur la voix vaut mieux que de couper les aigus du master.",
     "Too much sibilance? A de-esser on the vocal beats cutting the master's highs."),
    ("t.saturation", "tip", "Une légère saturation ajoute des harmoniques : la basse s'entend mieux sur petits haut-parleurs.",
     "Light saturation adds harmonics: the bass comes through better on small speakers."),
    ("t.ab", "tip", "▶ Original / ▶ Master gardent la position : idéal pour comparer le même passage.",
     "▶ Original / ▶ Master keep the position: ideal to compare the same passage."),
    ("t.cleanse", "tip", "Au-delà de 70 %, le nettoyage Anti-Parasite devient affirmé : monte par petites étapes.",
     "Above 70%, the Anti-Parasite cleanse gets assertive: raise it in small steps."),
    ("t.names", "tip", "Coche « BPM et tonalité dans les noms de fichiers » pour retrouver tes sons d'un coup d'œil.",
     "Tick 'Add BPM and key to the file names' to find your tracks at a glance."),

    # ---- while a batch runs -------------------------------------------------
    ("a.go", "action", "C'est parti, je danse pendant que ça masterise !", "Here we go, I dance while it masters!"),
    ("a.grind", "action", "Ça mouline… et moi aussi.", "It's crunching… and so am I."),
    ("a.clean", "action", "Je nettoie les parasites en rythme.", "Cleaning the parasites in time with the beat."),
    ("a.limiter", "action", "Le limiteur chauffe, moi aussi !", "The limiter is warming up, and so am I!"),
    ("a.patience", "action", "Patience, le son se fait beau.", "Patience, the sound is getting ready."),
    ("a.drop", "action", "Encore un peu… je sens déjà le drop.", "Almost there… I can already feel the drop."),

    # ---- v1.3: the lively studio buddy -------------------------------------------
    ("m.boss", "mascot", "C'est moi le patron du true peak ici. Personne ne dépasse -1 dBTP sans mon autorisation !",
     "I'm the boss of true peak around here. Nobody goes over -1 dBTP without my permission!"),
    ("m.coffee2", "mascot", "Trois cafés et un limiteur : ma recette du bonheur.", "Three coffees and a limiter: my recipe for happiness."),
    ("m.golden", "mascot", "J'ai des oreilles en or… enfin en silicium, mais elles brillent pareil.",
     "I've got golden ears… well, silicon ones, but they shine just the same."),
    ("m.potential", "mascot", "Ce morceau a du potentiel. Moi aussi d'ailleurs, regarde comme je flotte.",
     "This track has potential. So do I, by the way: look at me float."),
    ("m.phase", "mascot", "Je ne dors pas, je médite sur la phase.", "I'm not sleeping, I'm meditating on phase."),
    ("m.faint", "mascot", "Si j'entends un clip, je fais un malaise. Un vrai.", "If I hear a clip, I'll faint. For real."),
    ("m.monocheck", "mascot", "J'ai écouté ton mix en mono. Il faut qu'on parle… non, c'est bon, ça tient !",
     "I listened to your mix in mono. We need to talk… no wait, it holds up!"),
    ("m.sublove", "mascot", "Les sub-basses et moi, c'est une longue histoire d'amour.", "Sub-bass and me: a long love story."),
    ("m.fan", "mascot", "Je suis ton premier fan. Le deuxième, c'est ton voisin, mais il ne le sait pas encore.",
     "I'm your first fan. The second is your neighbour, he just doesn't know it yet."),
    ("m.water", "mascot", "Pense à boire de l'eau. Moi, je carbure aux décibels.", "Remember to drink water. I run on decibels."),
    ("m.legend", "mascot", "Un jour, on racontera que tout a commencé ici, dans ce studio.",
     "One day they'll say it all started here, in this studio."),
    ("m.chorus", "mascot", "Je suis un pro : je ne juge jamais un mix avant le refrain.",
     "I'm a pro: I never judge a mix before the chorus."),
    ("m.louder", "mascot", "Plus fort ? Toujours plus fort ? Calme-toi, champion, les plateformes vont te baisser.",
     "Louder? Always louder? Easy, champ, the platforms will turn you down anyway."),
    ("m.snare", "mascot", "Cette caisse claire, je la sens jusque dans mes pixels.", "I can feel that snare all the way down to my pixels."),
    ("m.holiday", "mascot", "Après ce batch, je prends des vacances. Trois secondes, pas plus.",
     "After this batch I'm taking a holiday. Three seconds, tops."),
    ("m.kick", "mascot", "Mets-moi un kick bien rond et je te fais un spectacle.", "Give me a nice round kick and I'll put on a show."),
    ("m.hero", "mascot", "Ni cape ni masque : juste un limiteur et beaucoup de passion.",
     "No cape, no mask: just a limiter and a lot of passion."),
    ("m.critic", "mascot", "Hmm… intéressant. Très intéressant. Bon, je n'ai rien compris, mais ça groove.",
     "Hmm… interesting. Very interesting. OK, I didn't get it, but it grooves."),
    ("m.night", "mascot", "Il est tard ? Les meilleurs masters se font quand tout le monde dort.",
     "Late? The best masters are made while everyone's asleep."),
    ("m.logo", "mascot", "Encore quelques batchs et je pourrai toucher le logo.", "A few more batches and I'll be able to touch the logo."),
    ("m.ego", "mascot", "Si ça sonne bien, c'est grâce à toi. Si ça sonne très bien, c'est un peu grâce à moi.",
     "If it sounds good, that's you. If it sounds great, that's a little bit me."),

    ("a.sweat", "action", "Eh oh, je transpire sur les basses là, laisse-moi calculer !",
     "Hey, I'm sweating over the bass here, let me crunch the numbers!"),
    ("a.parasite", "action", "J'ai senti un parasite passer dans les aigus… je m'en occupe.",
     "I felt a parasite sneak through the highs… I'm on it."),
    ("a.chef", "action", "Ne touche plus à rien, le chef est en train de sculpter le son.",
     "Don't touch anything, the chef is sculpting the sound."),
    ("a.fft", "action", "Je découpe ton son en milliers de fréquences… et je les recolle, promis.",
     "I'm slicing your sound into thousands of frequencies… and gluing them back, promise."),
    ("a.archer", "action", "Je vise la cible LUFS comme un archer. Ne bouge pas.", "Aiming at the LUFS target like an archer. Don't move."),
    ("a.watch", "action", "Un pic qui dépasse ? Pas sous ma garde.", "A peak sticking out? Not on my watch."),
    ("a.oven", "action", "Le master est au four. Encore quelques secondes de cuisson.",
     "The master is in the oven. A few more seconds to bake."),
    ("a.count", "action", "Chut… je compte les échantillons. 44 099, 44 100…", "Shh… I'm counting samples. 44,099, 44,100…"),
    ("a.pushups", "action", "Je fais des pompes avec ta compression.", "Doing push-ups with your compression."),
    ("a.trim", "action", "Je coupe les silences à la milliseconde près.", "Trimming the silences to the millisecond."),

    ("l.neighbour", "listen", "Encore un drop qui va faire vibrer les enceintes du voisin.",
     "Another drop that's going to rattle the neighbour's speakers."),
    ("l.dance", "listen", "Je danse ! Ne t'arrête pas, c'est trop bon.", "I'm dancing! Don't stop, it's too good."),
    ("l.ab", "listen", "Original ou master ? Ferme les yeux et écoute la différence.",
     "Original or master? Close your eyes and listen to the difference."),
    ("l.groove", "listen", "Ça groove ! Mes pieds n'ont pas eu le choix.", "That grooves! My feet had no choice."),
    ("l.volume", "listen", "Écoute à ton volume habituel : tes oreilles te remercieront.",
     "Listen at your usual volume: your ears will thank you."),
    ("l.chills", "listen", "Attends le refrain… voilà. Frissons.", "Wait for the chorus… there. Chills."),

    # ---- v1.3: the mastering teacher ------------------------------------------------
    ("p.lufs", "tip", "LUFS intégré = volume perçu moyen du morceau ; le LUFS court terme suit chaque passage.",
     "Integrated LUFS = average perceived loudness of the track; short-term LUFS follows each passage."),
    ("p.lra", "tip", "La plage de loudness (LRA) mesure l'écart entre passages calmes et forts : trop faible = mix écrasé.",
     "Loudness range (LRA) measures quiet vs loud passages: too low means a squashed mix."),
    ("p.plr", "tip", "Le rapport crête / volume (PLR) montre la place des transitoires : plus il est bas, plus c'est compressé.",
     "Peak-to-loudness ratio (PLR) shows the room for transients: the lower, the more compressed."),
    ("p.tp", "tip", "Un fichier peut culminer à -0,1 dBFS et saturer à l'encodage : surveille le true peak, pas la crête.",
     "A file can peak at -0.1 dBFS and still clip once encoded: watch the true peak, not the sample peak."),
    ("p.gainstaging", "tip", "Gain staging : vise environ -18 dBFS RMS par piste en mixant, le master aura de la place.",
     "Gain staging: aim for about -18 dBFS RMS per track while mixing, the master will have room."),
    ("p.bus", "tip", "Retire le limiteur du bus master avant d'exporter le mix à masteriser.",
     "Remove the limiter from your master bus before exporting the mix for mastering."),
    ("p.export", "tip", "Exporte le mix en 24 bits (ou 32 bits flottant), à la fréquence du projet, sans normaliser.",
     "Export the mix in 24-bit (or 32-bit float), at the project's sample rate, without normalising."),
    ("p.dither", "tip", "Le dither ne sert qu'à la dernière réduction de bits : une seule fois, à la toute fin.",
     "Dither is only for the last bit-depth reduction: once, at the very end."),
    ("p.sections", "tip", "Compare des passages équivalents : refrain contre refrain, couplet contre couplet.",
     "Compare equivalent sections: chorus against chorus, verse against verse."),
    ("p.refstyle", "tip", "Une référence trop différente en tempo ou en instruments fausse la comparaison tonale.",
     "A reference too different in tempo or instruments skews the tonal comparison."),
    ("p.lowend", "tip", "Basse et kick se partagent 40-120 Hz : décide lequel passe sous l'autre.",
     "Bass and kick share 40-120 Hz: decide which one sits under the other."),
    ("p.mud", "tip", "Trop de 200-400 Hz = son boueux ; une petite coupe large éclaircit tout le mix.",
     "Too much 200-400 Hz = a muddy sound; a small wide cut clears up the whole mix."),
    ("p.harsh", "tip", "La dureté se cache souvent entre 2 et 5 kHz : l'oreille y est très sensible.",
     "Harshness often hides between 2 and 5 kHz: the ear is very sensitive there."),
    ("p.air", "tip", "Un léger shelf au-dessus de 10 kHz ajoute de l'air, mais gare aux sifflantes.",
     "A gentle shelf above 10 kHz adds air, but watch the sibilance."),
    ("p.monobass", "tip", "Garde le grave au centre (mono sous ~120 Hz) : clubs, vinyles et téléphones te diront merci.",
     "Keep the low end centred (mono below ~120 Hz): clubs, vinyl and phones will thank you."),
    ("p.correlation", "tip", "Une corrélation stéréo proche de 0 ou négative signale des problèmes de phase.",
     "A stereo correlation near 0 or below points to phase problems."),
    ("p.attack", "tip", "Attaque lente = transitoires qui passent et punch ; attaque rapide = son plus dense et contrôlé.",
     "Slow attack = transients through and punch; fast attack = a denser, more controlled sound."),
    ("p.glue", "tip", "Compression de bus : 1 à 2 dB de réduction suffisent pour « coller » le mix.",
     "Bus compression: 1 to 2 dB of gain reduction is enough to glue the mix."),
    ("p.limiterlast", "tip", "Le limiteur se place en dernier : rien après lui, sinon le true peak n'est plus garanti.",
     "The limiter goes last: nothing after it, or the true peak is no longer guaranteed."),
    ("p.dynamic", "tip", "-14 LUFS n'est pas une obligation : un master dynamique bien fait sonne bien même plus bas.",
     "-14 LUFS isn't mandatory: a well-made dynamic master sounds great even quieter."),
    ("p.club", "tip", "Pour le club, on monte souvent vers -9 à -7 LUFS, au prix de transitoires plus écrasées.",
     "For club play, masters often reach -9 to -7 LUFS, at the cost of flatter transients."),
    ("p.album", "tip", "Sur un EP ou un album, équilibre les morceaux entre eux à l'oreille, pas seulement au LUFS.",
     "On an EP or album, balance the tracks against each other by ear, not just by LUFS."),
    ("p.tail", "tip", "Laisse vivre la queue de réverb : l'auto-trim garde 120 ms après le dernier son.",
     "Let the reverb tail live: auto-trim keeps 120 ms after the last sound."),
    ("p.playlist", "tip", "Un début sans silence évite les blancs gênants dans les playlists.",
     "A start without silence avoids awkward gaps in playlists."),
    ("p.antiparasite", "tip", "Anti-Parasite vise les artefacts des sons générés par IA : commence vers 30-40 % et écoute.",
     "Anti-Parasite targets the artefacts of AI-generated audio: start around 30-40% and listen."),
    ("p.aimetal", "tip", "Sons IA : les artefacts métalliques se cachent souvent dans les aigus ; vérifie au casque.",
     "AI tracks: metallic artefacts often hide in the highs; check on headphones."),
    ("p.mp3check", "tip", "Écoute aussi ton MP3 exporté : l'encodage peut révéler des défauts inaudibles en WAV.",
     "Also listen to your exported MP3: encoding can reveal flaws you can't hear in the WAV."),
    ("p.tags", "tip", "Tags propres (titre, artiste, BPM, tonalité, pochette) = un fichier pro, prêt pour les DJ.",
     "Clean tags (title, artist, BPM, key, cover) = a pro file, ready for DJs."),
    ("p.cover3000", "tip", "La plupart des distributeurs demandent une pochette d'au moins 3000 × 3000 px.",
     "Most distributors ask for a cover of at least 3000 × 3000 px."),
    ("p.adapt", "tip", "Après 20 minutes sur le même son, l'oreille s'habitue : fais une pause avant de valider.",
     "After 20 minutes on the same sound your ear adapts: take a break before signing off."),
    ("p.smallspk", "tip", "Petit haut-parleur : si la basse disparaît, ajoute des harmoniques plutôt que du grave.",
     "Small speaker: if the bass disappears, add harmonics rather than more low end."),
    ("p.notch", "tip", "Une résonance qui siffle ? Coupe étroite et précise plutôt qu'un grand EQ qui abîme tout.",
     "A whistling resonance? A narrow, precise cut beats a broad EQ that damages everything."),
    ("p.meters", "tip", "Les mesures guident, l'oreille décide : un bon chiffre ne sauve pas un mauvais son.",
     "Meters guide, ears decide: a good number never saves a bad sound."),
    ("p.djtags", "tip", "BPM et tonalité dans les tags : les DJ peuvent caler ton morceau en un clic.",
     "BPM and key in the tags: DJs can beat-match your track in one click."),
    ("p.seek", "tip", "Clique sur la barre de lecture pour sauter au refrain et comparer Original / Master au même endroit.",
     "Click the seek bar to jump to the chorus and compare Original / Master at the same spot."),

    # ---- events ---------------------------------------------------------------
    ("e.hatch1", "hatch", "Crac ! Me voilà. Prêt à masteriser ?", "Crack! Here I am. Ready to master?"),
    ("e.hatch2", "hatch", "Bonjour le studio ! On fait quoi aujourd'hui ?", "Hello studio! What are we making today?"),
    ("e.hatch3", "hatch", "Je viens d'éclore et j'ai déjà envie de danser.", "Just hatched and I already want to dance."),
    ("e.grow1", "grow", "Un batch de plus : je grandis !", "One more batch: I'm growing!"),
    ("e.grow2", "grow", "Hop, une taille au-dessus. Continue !", "Pop, one size up. Keep going!"),
    ("e.growmax", "grow_max", "Taille maximale atteinte ! Je suis au top de ma forme.",
     "Maximum size reached! I'm in top shape."),
    ("e.done1", "batch_done", "Terminé ! Tes fichiers t'attendent.", "Done! Your files are waiting for you."),
    ("e.done2", "batch_done", "Mission accomplie, ça sonne !", "Mission accomplished, it sounds great!"),
    ("e.failed", "batch_failed", "Terminé, mais certains fichiers ont résisté : regarde les cartes en rouge.",
     "Done, but some files resisted: check the red cards."),
    ("e.cancelled", "batch_cancelled", "Pause ! Je reprends mon souffle.", "Paused! Catching my breath."),
)

# Small label shown before the phrase, per category (English source, translated by the UI).
CATEGORY_LABELS: Dict[str, str] = {"tip": N_("Tip"), "quote": N_("Studio"), "action": N_("Live")}

# How often each category comes up in the random rotation.
IDLE_WEIGHTS: Dict[str, float] = {"tip": 0.45, "mascot": 0.38, "quote": 0.17}
BUSY_WEIGHTS: Dict[str, float] = {"action": 0.55, "tip": 0.25, "mascot": 0.20}


@dataclass(frozen=True)
class Phrase:
    id: str
    category: str
    fr: str
    en: str

    def text(self, language: str) -> str:
        """Text in ``language``; falls back to English, then French."""
        if language == "fr":
            return self.fr or self.en
        if language == "en":
            return self.en or self.fr
        return PHRASE_TRANSLATIONS.get(language, {}).get(self.id) or self.en or self.fr


PHRASES: List[Phrase] = [Phrase(pid, category, _french_spacing(fr), en) for pid, category, fr, en in _DATA]
BY_ID: Dict[str, Phrase] = {phrase.id: phrase for phrase in PHRASES}


class PhraseDeck:
    """Random phrases without quick repeats (one shuffled pile per category)."""

    def __init__(self, rng: Optional[random.Random] = None) -> None:
        self._rng = rng or random.Random()
        self._piles: Dict[str, List[Phrase]] = {}
        self._last: Optional[str] = None

    def _draw(self, category: str) -> Optional[Phrase]:
        pile = self._piles.get(category)
        if not pile:
            pile = [phrase for phrase in PHRASES if phrase.category == category]
            if not pile:
                return None
            self._rng.shuffle(pile)
            if len(pile) > 1 and pile[-1].id == self._last:      # no repeat across reshuffles
                pile[0], pile[-1] = pile[-1], pile[0]
            self._piles[category] = pile
        phrase = pile.pop()
        self._last = phrase.id
        return phrase

    def next(self, busy: bool = False) -> Phrase:
        weights = BUSY_WEIGHTS if busy else IDLE_WEIGHTS
        categories = list(weights)
        category = self._rng.choices(categories, [weights[c] for c in categories])[0]
        return self._draw(category) or self._draw("tip")

    def event(self, name: str) -> Optional[Phrase]:
        return self._draw(name)
