"""
French translations: {English source text: French text}.

A missing entry simply shows the English text (automatic fallback), so this
file can be completed at any time. Keep the {placeholders} identical.
Spaces before : ? ! ; are turned into non-breaking spaces at the end of the file.
"""

from __future__ import annotations

FR = {
    # ---- header / window -----------------------------------------------------
    "CLEAN · MASTER · CONVERT": "NETTOYER · MASTERISER · CONVERTIR",
    "Anti-Parasite Filter, mastering and conversion": "Filtre Anti-Parasite, mastering et conversion",
    "Interface language": "Langue de l'interface",
    "FFmpeg missing": "FFmpeg absent",
    "M4A input and MP3 / M4A export need FFmpeg.\nmacOS: brew install ffmpeg\nWindows: winget install Gyan.FFmpeg\n"
    "or: pip install imageio-ffmpeg":
        "L'import M4A et l'export MP3 / M4A ont besoin de FFmpeg.\nmacOS : brew install ffmpeg\n"
        "Windows : winget install Gyan.FFmpeg\nou : pip install imageio-ffmpeg",
    "{path}\nfound via {source}": "{path}\ntrouvé via {source}",
    "No MP3 encoder in this build.": "Pas d'encodeur MP3 dans cette version.",
    "A batch is still running. Stop it and quit?": "Un traitement est encore en cours. L'arrêter et quitter ?",
    "Loading the audio engine…": "Chargement du moteur audio…",
    "Mastering": "Mastering",
    "Converter": "Convertisseur",

    # ---- companion -----------------------------------------------------------
    "Tip": "Astuce",
    "Studio": "Studio",
    "Live": "En direct",
    "Hide the bubble": "Masquer la bulle",
    "Show the phrases again": "Réafficher les phrases",
    "Level {level}/{max}: I grow with every batch you run in this session. Click me for another line.":
        "Niveau {level}/{max} : je grandis à chaque traitement lancé pendant cette session. "
        "Clique sur moi pour une autre phrase.",

    # ---- shared widgets --------------------------------------------------------
    "Next to the source files": "À côté des fichiers source",
    "In this folder:": "Dans ce dossier :",
    "Browse…": "Parcourir…",
    "Add files…": "Ajouter des fichiers…",
    "Add folder…": "Ajouter un dossier…",
    "Audio files ({patterns});;All files (*)": "Fichiers audio ({patterns});;Tous les fichiers (*)",
    "Choose the output folder": "Choisir le dossier de sortie",
    "Add audio files": "Ajouter des fichiers audio",
    "Add a folder": "Ajouter un dossier",
    "Clear list": "Vider la liste",
    "Cancel": "Annuler",
    "Show file": "Afficher le fichier",
    "Show folder": "Afficher le dossier",
    "Cannot use the output folder:\n{error}": "Impossible d'utiliser le dossier de sortie :\n{error}",
    "Batch finished: {details}.": "Traitement terminé : {details}.",
    "{n} failed": "{n} en échec",
    "cancelled": "annulé",
    "Ready": "Prêt",
    "Queued": "En attente",
    "Done": "Terminé",
    "Cancelled": "Annulé",
    "Failed": "Échec",
    "This FFmpeg build has no MP3 encoder (libmp3lame).": "Cette version de FFmpeg n'a pas d'encodeur MP3 (libmp3lame).",
    "Track {i}/{n} - {name}": "Piste {i}/{n} - {name}",
    "Play / pause": "Lecture / pause",
    "Click or drag to go to any moment of the track": "Clique ou fais glisser pour aller à n'importe quel moment du morceau",
    "File {i}/{n} - {name}": "Fichier {i}/{n} - {name}",

    # ---- mastering tab: sidebar -------------------------------------------------
    "Preset": "Preset",
    "⚙️  Advanced Settings": "⚙️  Réglages avancés",
    "Tone and dynamics recipe": "Recette de timbre et de dynamique",
    "EQ curve, compressor and saturation used by the mastering chain.":
        "Courbe d'EQ, compresseur et saturation utilisés par la chaîne de mastering.",
    "Limiter drive (target loudness)": "Attaque du limiteur (volume cible)",
    "How hard the mix is pushed into the limiter. Higher = louder and more limiting. "
    "Streaming platforms turn masters louder than -14 LUFS down.":
        "À quel point le mix est poussé dans le limiteur. Plus haut = plus fort et plus limité. "
        "Les plateformes de streaming baissent les masters plus forts que -14 LUFS.",
    "Limiter ceiling": "Plafond du limiteur",
    "Highest true peak allowed. -1.0 dBTP is the safe value for MP3 / AAC / streaming.":
        "True peak maximal autorisé. -1,0 dBTP est la valeur sûre pour le MP3 / AAC / streaming.",
    "Anti-Parasite intensity": "Intensité Anti-Parasite",
    "Spectral cleanse depth and phase / time micro-variation. 0% keeps only the "
    "20 Hz - 20 kHz band-limiting. Above ~70% the cleanse becomes assertive.":
        "Profondeur du nettoyage spectral et micro-variation de phase / temps. 0 % ne garde que la "
        "limitation de bande 20 Hz - 20 kHz. Au-delà de ~70 %, le nettoyage devient affirmé.",
    "Reset to preset values": "Revenir aux valeurs du preset",
    "Custom settings": "Réglages personnalisés",
    "Preset values": "Valeurs du preset",
    "cleanse {pct}": "nettoyage {pct}",
    "(reference)": "(référence)",
    "reference match": "correspondance à la référence",
    "auto-trim": "auto-trim",

    "🎯  Reference track": "🎯  Morceau de référence",
    "Load a reference…": "Charger une référence…",
    "Stop using the reference": "Ne plus utiliser la référence",
    "A commercial track whose sound you like. Its tonal balance and loudness become the targets.":
        "Un morceau du commerce dont tu aimes le son. Son équilibre tonal et son volume deviennent les cibles.",
    "Match the tonal balance (EQ)": "Copier l'équilibre tonal (EQ)",
    "Replaces the recipe EQ with a linear-phase EQ that moves the track's broad tonal balance towards the "
    "reference (half-octave smoothing, at most ±{db} dB). Compression, saturation and the limiter stay "
    "those of the recipe.":
        "Remplace l'EQ de la recette par un EQ à phase linéaire qui rapproche l'équilibre tonal global du "
        "morceau de celui de la référence (lissage à la demi-octave, ±{db} dB au maximum). La compression, "
        "la saturation et le limiteur restent ceux de la recette.",
    "Match strength": "Force de la correspondance",
    "How far to go towards the reference's tonal balance.": "Jusqu'où aller vers l'équilibre tonal de la référence.",
    "Match the loudness (target = reference LUFS)": "Copier le volume (cible = LUFS de la référence)",
    "Uses the reference's integrated loudness as the limiter target (kept between -20 and -6 LUFS). "
    "Your ceiling still applies.":
        "Utilise le volume intégré de la référence comme cible du limiteur (entre -20 et -6 LUFS). "
        "Ton plafond reste appliqué.",
    "Analysing {name}…": "Analyse de {name}…",
    "⚠ Could not use {name}: {error}": "⚠ Impossible d'utiliser {name} : {error}",
    "Tick an option below to use it.": "Coche une option ci-dessous pour l'utiliser.",
    "true peak {value} dBTP": "true peak {value} dBTP",
    "Choose a reference track": "Choisir un morceau de référence",
    "Audio ({patterns})": "Audio ({patterns})",
    "Analysing the reference…": "Analyse de la référence…",

    "✂️  Auto-trim and fades": "✂️  Auto-trim et fondus",
    "Cut the silence at the start and the end": "Couper le silence au début et à la fin",
    "After mastering: removes leading / trailing silence (10 ms kept before the first sound, 120 ms after "
    "the last) and adds anti-click fades (5 ms in, 20 ms out).":
        "Après le mastering : retire le silence au début et à la fin (10 ms gardées avant le premier son, "
        "120 ms après le dernier) et ajoute des fondus anti-clic (5 ms à l'entrée, 20 ms à la sortie).",
    "Silence threshold": "Seuil de silence",
    "Anything quieter than this at the edges counts as silence. -60 dBFS suits most tracks; raise it for "
    "noisy intros / tails.":
        "Tout ce qui est plus faible aux extrémités compte comme du silence. -60 dBFS convient à la plupart "
        "des morceaux ; monte-le pour les intros / fins bruitées.",

    "Export": "Export",
    "Add BPM and key to the file names": "BPM et tonalité dans les noms de fichiers",
    "Example: MyTrack_142BPM_Cm_HTD_Standard.wav": "Exemple : MonSon_142BPM_Cm_HTD_Standard.wav",
    "This export needs FFmpeg, which was not found.": "Cet export a besoin de FFmpeg, qui est introuvable.",
    "One folder per track: WAV 24-bit, MP3 320 kbps (ID3 tags + cover), cover.jpg, social clip and an "
    "info sheet.":
        "Un dossier par piste : WAV 24 bits, MP3 320 kbps (tags ID3 + pochette), cover.jpg, clip social et "
        "fiche d'infos.",
    "One folder per track: WAV 24-bit, MP3 320 kbps (ID3 tags + cover), cover.jpg and an info sheet.":
        "Un dossier par piste : WAV 24 bits, MP3 320 kbps (tags ID3 + pochette), cover.jpg et fiche d'infos.",
    "Lossy format: keep a WAV or FLAC master as well.": "Format avec perte : garde aussi un master WAV ou FLAC.",
    "Install FFmpeg or choose WAV / FLAC without a clip.": "Installe FFmpeg ou choisis WAV / FLAC sans clip.",

    "🏷️  Tags and cover": "🏷️  Tags et pochette",
    "Artist": "Artiste",
    "Album": "Album",
    "Year": "Année",
    "Genre": "Genre",
    "Single / EP name": "Nom du single / de l'EP",
    "No\ncover": "Pas de\npochette",
    "No cover": "Pas de pochette",
    "Choose a cover…": "Choisir une pochette…",
    "Remove cover": "Retirer la pochette",
    "Choose a cover image": "Choisir une image de pochette",
    "Images ({patterns})": "Images ({patterns})",
    "Title, BPM and key come from each track card. MP3, FLAC and M4A get the cover (square crop, 1400 px); "
    "WAV gets text tags only. The track number is written when an album is set.":
        "Le titre, le BPM et la tonalité viennent de chaque carte. MP3, FLAC et M4A reçoivent la pochette "
        "(recadrage carré, 1400 px) ; le WAV seulement les tags texte. Le numéro de piste est écrit quand "
        "un album est renseigné.",
    "The cover image was not found:\n{path}": "Image de pochette introuvable :\n{path}",

    "📱  Social clip": "📱  Clip réseaux sociaux",
    "Export a short clip (TikTok / Reels / Shorts)": "Exporter un extrait court (TikTok / Reels / Shorts)",
    "Best part (auto)": "Meilleur passage (auto)",
    "From the start": "Depuis le début",
    "Auto picks the most energetic passage and, when the BPM is known, starts on a beat and keeps whole bars.":
        "Auto choisit le passage le plus énergique et, si le BPM est connu, démarre sur un temps et garde "
        "des mesures entières.",
    "Also make a vertical video (1080×1920)": "Faire aussi une vidéo verticale (1080×1920)",
    "M4A (AAC 256 kbps) with a 0.25 s fade-in and a 1.5 s fade-out. The video shows the cover on a blurred "
    "background.":
        "M4A (AAC 256 kbps) avec un fondu d'entrée de 0,25 s et de sortie de 1,5 s. La vidéo montre la "
        "pochette sur un fond flouté.",
    "Needs a cover image and an FFmpeg build with a video encoder.":
        "Il faut une pochette et une version de FFmpeg avec un encodeur vidéo.",
    "Choose a cover in 'Tags and cover' first.": "Choisis d'abord une pochette dans « Tags et pochette ».",
    "H.264 video ({encoder}) with the clip's audio.": "Vidéo H.264 ({encoder}) avec le son du clip.",

    # ---- mastering tab: list + footer ------------------------------------------
    "Drop tracks or folders here": "Dépose des morceaux ou des dossiers ici",
    "WAV, MP3, M4A, FLAC, OGG, AIFF - folders are scanned for audio files.":
        "WAV, MP3, M4A, FLAC, OGG, AIFF - les dossiers sont parcourus pour trouver l'audio.",
    "No tracks yet": "Aucune piste pour l'instant",
    "{n} track": "{n} piste",
    "{n} tracks": "{n} pistes",
    "Add tracks to begin.": "Ajoute des pistes pour commencer.",
    "Master": "Master",
    "Export {n} track as {what}": "Exporter {n} piste en {what}",
    "Export {n} tracks as {what}": "Exporter {n} pistes en {what}",
    "release packs": "packs de sortie",
    "Working…": "Traitement…",
    "Cancelling after the current step…": "Annulation après l'étape en cours…",
    "{n} done": "{n} terminée(s)",

    # ---- track card --------------------------------------------------------------
    "Remove from the list": "Retirer de la liste",
    "Track title: used for the tags and the exported file names.":
        "Titre de la piste : utilisé pour les tags et les noms des fichiers exportés.",
    "Tempo. 0 = unknown. Detection can land on half or double the tempo on some styles: use ÷2 / ×2.":
        "Tempo. 0 = inconnu. Sur certains styles, la détection peut tomber sur la moitié ou le double : "
        "utilise ÷2 / ×2.",
    "Half tempo": "Moitié du tempo",
    "Double tempo": "Double du tempo",
    "Musical key (Camelot code for harmonic mixing).": "Tonalité (code Camelot pour le mix harmonique).",
    "Back to the detected BPM and key": "Revenir au BPM et à la tonalité détectés",
    "Detecting BPM and key…": "Détection du BPM et de la tonalité…",
    "BPM / key detection failed: {error}": "Échec de la détection BPM / tonalité : {error}",
    "BPM / key not detected": "BPM / tonalité non détectés",
    "no steady beat or key": "pas de pulsation ni de tonalité nettes",
    "Detected: {what}": "Détecté : {what}",
    "Tempo confidence {bpm}% · key confidence {key}%. Both stay editable.":
        "Fiabilité tempo {bpm} % · fiabilité tonalité {key} %. Les deux restent modifiables.",
    "Original": "Original",
    "Mastered": "Masterisé",
    "True peak": "True peak",
    "Limiter": "Limiteur",
    "⚖️ Gain Match (A/B)": "⚖️ Gain Match (A/B)",
    "Plays both versions at the same loudness (LUFS) so you judge the processing, not the volume. "
    "Listening only: the exported file keeps its full level.":
        "Lit les deux versions au même volume (LUFS) pour juger le traitement et non le niveau. "
        "Écoute seulement : le fichier exporté garde tout son niveau.",
    "Analysis…": "Analyse…",
    "Waiting in the queue": "Dans la file d'attente",
    "Processing": "En cours",
    "Processing was cancelled.": "Le traitement a été annulé.",
    "Stereo": "Stéréo",
    "Mono": "Mono",
    "{rate} Hz source": "source {rate} Hz",
    "{recipe} recipe": "recette {recipe}",
    "{pct}% cleanse": "nettoyage {pct} %",
    "target {target} · {delta}": "cible {target} · {delta}",
    "ceiling {value} dBTP": "plafond {value} dBTP",
    "max gain reduction": "réduction de gain max",
    "✂️ Trimmed {start} s at the start, {end} s at the end": "✂️ {start} s coupées au début, {end} s à la fin",
    "✂️ Auto-trim: no silence to remove": "✂️ Auto-trim : aucun silence à couper",
    "🎯 Matched to {name}": "🎯 Calé sur {name}",
    "tonal distance {before} → {after} dB": "écart tonal {before} → {after} dB",
    "loudness {value} LUFS": "volume {value} LUFS",
    "Export failed: {error}": "Échec de l'export : {error}",
    "On target": "Dans la cible",
    "Check": "À vérifier",

    # ---- analysis window ---------------------------------------------------------
    "Analysis - {name}": "Analyse - {name}",
    "Logarithmic": "Logarithmique",
    "Linear (top octave in detail)": "Linéaire (octave haute en détail)",
    "Frequency scale:": "Échelle des fréquences :",
    "Rendering…": "Rendu en cours…",
    "Spectrograms": "Spectrogrammes",
    "Tonal balance": "Équilibre tonal",
    "Specs and report": "Mesures et rapport",
    "Could not render: {error}": "Rendu impossible : {error}",
    "No tonal comparison available for this track.": "Pas de comparaison tonale disponible pour cette piste.",
    "Tempo and key": "Tempo et tonalité",
    "Detected: {bpm} BPM (confidence {bpm_conf}%), {key} (confidence {key_conf}%).":
        "Détecté : {bpm} BPM (fiabilité {bpm_conf} %), {key} (fiabilité {key_conf} %).",
    "Beat grid phase {value} s (social clips start on a beat).":
        "Phase de la grille rythmique {value} s (les clips sociaux démarrent sur un temps).",
    "Reference matching": "Correspondance à la référence",
    "Reference: {name}.": "Référence : {name}.",
    "Linear-phase match EQ (replaces the recipe EQ): up to {boost} dB / {cut} dB, broad curve smoothed "
    "over half an octave.":
        "EQ de correspondance à phase linéaire (remplace l'EQ de la recette) : jusqu'à {boost} dB / "
        "{cut} dB, courbe large lissée sur une demi-octave.",
    "Average tonal-balance distance to the reference (60 Hz - 12 kHz): {before} dB before -> {after} dB after.":
        "Écart moyen d'équilibre tonal avec la référence (60 Hz - 12 kHz) : {before} dB avant -> "
        "{after} dB après.",
    "Loudness target taken from the reference: {value} LUFS.": "Volume cible pris sur la référence : {value} LUFS.",
    "Auto-trim": "Auto-trim",
    "Removed {start} s of silence at the start and {end} s at the end, with 5 ms / 20 ms anti-click fades.":
        "{start} s de silence retirées au début et {end} s à la fin, avec fondus anti-clic de 5 ms / 20 ms.",
    "No silence to remove at either end.": "Aucun silence à retirer aux extrémités.",
    "Anti-Parasite Filter": "Filtre Anti-Parasite",
    "Intensity {pct}% - band-limited to 20 Hz - 20 kHz (zero-phase).":
        "Intensité {pct} % - bande limitée à 20 Hz - 20 kHz (phase nulle).",
    "(+{n} more)": "(+{n} autres)",
    "Time-locked tonal lines removed: {lines} - up to {db} dB.":
        "Raies tonales fixes retirées : {lines} - jusqu'à {db} dB.",
    "No time-locked tonal lines were detected.": "Aucune raie tonale fixe détectée.",
    "Stationary residue: soft mask, at most {db} dB on cells at the noise floor.":
        "Résidu stationnaire : masque doux, {db} dB au maximum sur les cellules au niveau du bruit de fond.",
    "Phase micro-variation up to +/-{deg} degrees (none below 80 Hz); time drift up to +/-{us} microseconds "
    "(< {cents} cent). Identical on both channels.":
        "Micro-variation de phase jusqu'à +/-{deg} degrés (aucune sous 80 Hz) ; dérive temporelle jusqu'à "
        "+/-{us} microsecondes (< {cents} cent). Identique sur les deux canaux.",
    "{profile}: input {lufs_in} LUFS -> output {lufs_out} LUFS, true peak {peak} dBTP.":
        "{profile} : entrée {lufs_in} LUFS -> sortie {lufs_out} LUFS, true peak {peak} dBTP.",
    "Gain into the limiter {gain} dB, maximum gain reduction {gr} dB, {passes} normalisation pass(es), "
    "processing time {seconds} s.":
        "Gain vers le limiteur {gain} dB, réduction de gain maximale {gr} dB, {passes} passe(s) de "
        "normalisation, durée de traitement {seconds} s.",

    # ---- converter tab -----------------------------------------------------------
    "Convert to": "Convertir en",
    "Sample rate": "Fréquence d'échantillonnage",
    "Output": "Sortie",
    "Converts with FFmpeg only - no mastering, no cleaning. Tags (title, artist...) are copied when the "
    "format supports them.":
        "Conversion par FFmpeg uniquement - ni mastering, ni nettoyage. Les tags (titre, artiste…) sont "
        "copiés quand le format les gère.",
    "Drop files or folders to convert": "Dépose des fichiers ou des dossiers à convertir",
    "Any audio FFmpeg can read (WAV, MP3, M4A, FLAC, OGG, OPUS, AIFF, WMA...) and the audio track of video files.":
        "Tout audio lisible par FFmpeg (WAV, MP3, M4A, FLAC, OGG, OPUS, AIFF, WMA…) et la piste son des vidéos.",
    "No files yet": "Aucun fichier pour l'instant",
    "{n} file": "{n} fichier",
    "{n} files": "{n} fichiers",
    "Add files to begin.": "Ajoute des fichiers pour commencer.",
    "Convert": "Convertir",
    "Convert {n} file to {what}": "Convertir {n} fichier en {what}",
    "Convert {n} files to {what}": "Convertir {n} fichiers en {what}",
    "Converting": "Conversion",
    "Converting…": "Conversion…",
    "{n} converted": "{n} converti(s)",
    "FFmpeg was not found: the converter needs it.": "FFmpeg est introuvable : le convertisseur en a besoin.",
    "MP3 cannot store 96 kHz: FFmpeg will use 48 kHz.": "Le MP3 ne gère pas le 96 kHz : FFmpeg utilisera 48 kHz.",
    "Reducing to 16 bits uses triangular dither.": "Le passage en 16 bits utilise un dither triangulaire.",


    # ---- engine texts (labels, presets, progress, tables, errors) ----------------------
    "WAV 24-bit": "WAV 24 bits",
    "MP3 320 kbps": "MP3 320 kbps",
    "M4A (AAC 256 kbps)": "M4A (AAC 256 kbps)",
    "48 kHz": "48 kHz",
    "96 kHz": "96 kHz",
    "WAV 16-bit (dithered)": "WAV 16 bits (avec dither)",
    "FLAC 24-bit": "FLAC 24 bits",
    "Release pack (WAV 24-bit + MP3 320 + cover)": "Pack de sortie (WAV 24 bits + MP3 320 + pochette)",
    "Keep original": "Garder l'original",
    "44.1 kHz": "44,1 kHz",
    "Balanced streaming master with gentle glue compression.":
        "Master streaming équilibré avec une compression de cohésion douce.",
    "Sub-bass weight and punch: slow-attack compression lets the drums hit.":
        "Poids dans les infra-basses et punch : une compression à attaque lente laisse frapper la batterie.",
    "Club-loud master. Expect audible limiting on very dynamic mixes.":
        "Master fort façon club. Limitation audible attendue sur les mix très dynamiques.",
    "Almost no compression: dynamics and transients preserved, quieter by design.":
        "Presque pas de compression : dynamique et transitoires préservées, volume plus bas par choix.",
    "Decoding": "Décodage",
    "Measuring the original": "Mesure de l'original",
    "Measuring the cleaned version": "Mesure de la version nettoyée",
    "Matching the reference tonal balance": "Calage sur l'équilibre tonal de la référence",
    "Trimming silences": "Coupe des silences",
    "Analysing the master": "Analyse du master",
    "Writing the master cache and preview": "Écriture du master et de l'écoute",
    "Exporting": "Export",
    "Exporting + clip": "Export + clip",
    "Anti-Parasite Filter: band-limiting 20 Hz - 20 kHz": "Filtre Anti-Parasite : limitation de bande 20 Hz - 20 kHz",
    "Anti-Parasite Filter: analysing stationary spectral content":
        "Filtre Anti-Parasite : analyse du contenu spectral stationnaire",
    "Anti-Parasite Filter: spectral cleanse and phase micro-smoothing":
        "Filtre Anti-Parasite : nettoyage spectral et micro-lissage de phase",
    "Anti-Parasite Filter: done": "Filtre Anti-Parasite : terminé",
    "Mastering: measuring input loudness": "Mastering : mesure du volume d'entrée",
    "Mastering: harmonic saturation": "Mastering : saturation harmonique",
    "Mastering: verifying true peak": "Mastering : vérification du true peak",
    "Mastering: done": "Mastering : terminé",
    "Mastering: true-peak analysis": "Mastering : analyse du true peak",
    "Mastering: loudness target reached": "Mastering : volume cible atteint",
    "Version": "Version",
    "Loudness (LUFS)": "Volume (LUFS)",
    "True peak (dBTP)": "True peak (dBTP)",
    "Sample peak (dBFS)": "Crête échantillon (dBFS)",
    "Peak-to-loudness (dB)": "Crête / volume (dB)",
    "Stereo correlation": "Corrélation stéréo",
    "Cleaned": "Nettoyé",
    "Band": "Bande",
    "Sub (20-60 Hz)": "Sub (20-60 Hz)",
    "Bass (60-250 Hz)": "Basses (60-250 Hz)",
    "Low mids (250-500 Hz)": "Bas médiums (250-500 Hz)",
    "Mids (500 Hz-2 kHz)": "Médiums (500 Hz-2 kHz)",
    "High mids (2-6 kHz)": "Hauts médiums (2-6 kHz)",
    "Highs (6-12 kHz)": "Aigus (6-12 kHz)",
    "Air (12-20 kHz)": "Air (12-20 kHz)",
    "Not enough memory to process this track.": "Pas assez de mémoire pour traiter cette piste.",
    "The reference track is not loaded any more - load it again.":
        "Le morceau de référence n'est plus chargé : charge-le à nouveau.",
    "The reference track is too quiet to be measured.": "Le morceau de référence est trop faible pour être mesuré.",
    "Only a mastered track can be exported.": "Seule une piste masterisée peut être exportée.",
    "Install Pillow to use this cover image format.": "Installe Pillow pour utiliser ce format d'image.",
    "The vertical video needs Pillow: pip install Pillow": "La vidéo verticale a besoin de Pillow : pip install Pillow",
    "The file no longer exists.": "Le fichier n'existe plus.",
    "The uploaded file is empty.": "Le fichier est vide.",
    "The file contains no audio data.": "Le fichier ne contient pas d'audio.",
    "Invalid sample rate for conversion.": "Fréquence d'échantillonnage invalide pour la conversion.",
    "Invalid sample rate.": "Fréquence d'échantillonnage invalide.",
    "The file is silent - there is nothing to process.": "Le fichier est silencieux : il n'y a rien à traiter.",
    "The audio is too short for a loudness measurement.": "L'audio est trop court pour une mesure de volume.",
    "The audio is too short for the Anti-Parasite Filter.": "L'audio est trop court pour le Filtre Anti-Parasite.",
    "The Anti-Parasite Filter produced invalid samples.": "Le Filtre Anti-Parasite a produit des échantillons invalides.",
    "The effects chain returned audio with an unexpected shape.":
        "La chaîne d'effets a renvoyé un audio de forme inattendue.",
    "The effects chain produced invalid samples.": "La chaîne d'effets a produit des échantillons invalides.",
    "The processed signal is too quiet to normalise.": "Le signal traité est trop faible pour être normalisé.",
    "The track is too quiet for a loudness measurement (below the -70 LUFS gate).":
        "La piste est trop faible pour une mesure de volume (sous le seuil de -70 LUFS).",
    "Non-finite samples (NaN/Inf) were found and replaced with silence.":
        "Des échantillons non finis (NaN/Inf) ont été trouvés et remplacés par du silence.",
    "encode the clip": "encoder le clip",
    "make the video": "créer la vidéo",
    "write the tags": "écrire les tags",

    # ---- v2.0: listen first, export later; loop, mono, phase, profiles, conflicts ----------
    "Free & Open Edition": "Édition Libre & Gratuite",
    "{version}: correlation {corr}, bass (below 150 Hz) {bass}, worst moment {worst}, mono fold-down {mono} dB, width (side / mid) {width} dB.":
        "{version} : corrélation {corr}, basses (sous 150 Hz) {bass}, pire passage {worst}, repli mono {mono} dB, largeur (side / mid) {width} dB.",
    "Stereo and phase (mono compatibility)":
        "Stéréo et phase (compatibilité mono)",
    "mono file: nothing can cancel":
        "fichier mono : rien ne peut s'annuler",
    "Rename (_2, _3…)":
        "Renommer (_2, _3…)",
    "Overwrite":
        "Écraser",
    "Skip":
        "Ignorer",
    "reference loudness":
        "volume de la référence",
    "One subfolder per mode (…/Club/, …/Streaming/)":
        "Un sous-dossier par mode (…/Club/, …/Streaming/)",
    "Each export goes into a subfolder named after its preset, so several modes of the same track can sit side by side.":
        "Chaque export va dans un sous-dossier au nom de son preset : plusieurs modes d'une même piste peuvent cohabiter.",
    "Export without metadata (100% blank files)":
        "Exporter sans métadonnées (fichiers 100 % vierges)",
    "Writes the audio only: no title, artist, album, BPM, key or cover, and no software / encoder signature. Source tags are always stripped either way.":
        "Écrit l'audio seul : ni titre, artiste, album, BPM, tonalité ou pochette, ni signature de logiciel / d'encodeur. Les tags du fichier source sont de toute façon toujours retirés.",
    "Turned off while 'Export without metadata' is ticked.":
        "Désactivé tant que « Exporter sans métadonnées » est coché.",
    "Rename keeps both files (name_2, name_3…). Overwrite replaces the old file. Skip leaves it untouched and writes nothing for that track.":
        "Renommer garde les deux fichiers (nom_2, nom_3…). Écraser remplace l'ancien fichier. Ignorer le laisse intact et n'écrit rien pour cette piste.",
    "If the file already exists:":
        "Si le fichier existe déjà :",
    "⬇ Export all":
        "⬇ Tout exporter",
    "🎧 Prepare the previews":
        "🎧 Préparer l'écoute",
    "New mode ready: playback follows at the same moment.":
        "Nouveau mode prêt : la lecture continue au même moment.",
    "Profiles":
        "Profils",
    "Your favourite combinations (mode, recipe, Anti-Parasite, auto-trim, export). 💾 saves the current settings.":
        "Vos combinaisons favorites (mode, recette, Anti-Parasite, auto-trim, export). 💾 enregistre les réglages actuels.",
    "✓ All tracks exported":
        "✓ Toutes les pistes sont exportées",
    "1. Prepare the previews · 2. Listen and compare · 3. Export":
        "1. Préparer l'écoute · 2. Écouter et comparer · 3. Exporter",
    "{n} skipped (file already there)":
        "{n} ignorée(s) (fichier déjà présent)",
    "Export finished: {details}.":
        "Export terminé : {details}.",
    "Previews ready: {details}. Listen, compare, then export.":
        "Écoute prête : {details}. Écoutez, comparez, puis exportez.",
    "✓ All previews ready":
        "✓ Toutes les écoutes sont prêtes",
    "Prepare {n} preview":
        "Préparer l'écoute de {n} piste",
    "Prepare {n} previews":
        "Préparer l'écoute de {n} pistes",
    "Choose a profile to apply its settings":
        "Choisissez un profil pour appliquer ses réglages",
    "— My profiles —":
        "— Mes profils —",
    "Profile name:":
        "Nom du profil :",
    "Save profile":
        "Enregistrer le profil",
    "Rename profile":
        "Renommer le profil",
    "Delete the profile “{name}”?":
        "Supprimer le profil « {name} » ?",
    "My settings":
        "Mes réglages",
    "Replace the profile “{name}”?":
        "Remplacer le profil « {name} » ?",
    "bass {bass} · mono {mono} dB":
        "basses {bass} · mono {mono} dB",
    "Correlation {value} (+1 = mono, 0 = very wide, below 0 = out of phase). Width (side / mid) {width} dB.":
        "Corrélation {value} (+1 = mono, 0 = très large, sous 0 = hors phase). Largeur (side / mid) {width} dB.",
    "Check it by ear with the Mono button.":
        "Vérifiez à l'oreille avec le bouton Mono.",
    "Listen in mono (left + right summed), like a phone or a club system: reveals what cancels. Listening only, the export stays stereo.":
        "Écoute en mono (gauche + droite additionnés), comme un téléphone ou une sono de club : révèle ce qui s'annule. Écoute seulement, l'export reste en stéréo.",
    "Rendered modes:":
        "Modes calculés :",
    "Modes already rendered for this track (kept for this session): click one to switch back instantly.":
        "Modes déjà calculés pour cette piste (gardés pendant la session) : cliquez sur l'un d'eux pour y revenir instantanément.",
    "Write this track's files (format, tags, cover, clip) to the output folder.":
        "Écrit les fichiers de cette piste (format, tags, pochette, clip) dans le dossier de sortie.",
    "Mono source: no phase risk.":
        "Source mono : aucun risque de phase.",
    "⚠ The bass is not centred (correlation {value} below 150 Hz): it can thin out or vanish in mono (club systems, phones, vinyl).":
        "⚠ Les basses ne sont pas centrées (corrélation {value} sous 150 Hz) : elles peuvent maigrir ou disparaître en mono (sono de club, téléphone, vinyle).",
    "⚠ Some passages are out of phase (worst moment {value}): they cancel when left and right are summed.":
        "⚠ Certains passages sont hors phase (pire moment {value}) : ils s'annulent quand gauche et droite sont additionnés.",
    "⚠ The track loses {db} dB when summed to mono: very wide or out-of-phase content.":
        "⚠ La piste perd {db} dB en mono : contenu très large ou hors phase.",
    "Mono-compatible: nothing cancels when left and right are summed.":
        "Compatible mono : rien ne s'annule quand gauche et droite sont additionnés.",
    "Stereo / phase":
        "Stéréo / phase",
    "not measured":
        "non mesuré",
    "You are hearing the preview made with {mode}. Prepare the previews to hear the current settings, or pick a rendered mode below.":
        "Vous écoutez la version calculée avec {mode}. Préparez l'écoute pour entendre les réglages actuels, ou choisissez un mode calculé ci-dessous.",
    "Other settings":
        "Autres réglages",
    "The export uses the current settings: they are rendered first.":
        "L'export utilise les réglages actuels : ils sont calculés d'abord.",
    "⬇ Render + export":
        "⬇ Calculer + exporter",
    "Original: correlation {value}, bass {bass}.":
        "Original : corrélation {value}, basses {bass}.",
    "✓ Exported: {name}":
        "✓ Exporté : {name}",
    "✓ Exported":
        "✓ Exporté",
    "Title, BPM, key, tags or format changed: export again (no new mastering).":
        "Titre, BPM, tonalité, tags ou format modifiés : exportez à nouveau (sans nouveau mastering).",
    "⬇ Export again":
        "⬇ Réexporter",
    "⬇ Export":
        "⬇ Exporter",
    "Skipped: {name} already exists (rule: skip).":
        "Ignoré : {name} existe déjà (règle : ignorer).",
    "⏭ Skipped":
        "⏭ Ignoré",
    "Preview only: nothing written yet.":
        "Écoute seulement : rien n'est encore écrit.",
    "Loop between A and B (kept when you switch Original / Master or the mode)":
        "Boucle entre A et B (gardée quand vous passez d'Original à Master ou changez de mode)",
    "Checking stereo and phase":
        "Vérification de la stéréo et de la phase",
    "Preview ready":
        "Écoute prête",
    "Loop start (A): set it at the current moment":
        "Début de boucle (A) : le placer à l'instant présent",
    "Loop end (B): set it at the current moment":
        "Fin de boucle (B) : la placer à l'instant présent",
    "Clear the loop":
        "Effacer la boucle",
    "Save the current settings as a profile":
        "Enregistrer les réglages actuels comme profil",
    "Rename the selected profile":
        "Renommer le profil sélectionné",
    "Delete the selected profile":
        "Supprimer le profil sélectionné",
    # ---- v2.0.1: PortAudio player ----------
    "No sound output available: {error}": "Aucune sortie audio disponible : {error}",
    "The preview could not be prepared:\n{error}": "L'écoute n'a pas pu être préparée :\n{error}",
    "The audio output stopped (device disconnected?).": "La sortie audio s'est arrêtée (périphérique débranché ?).",
    # ---- v2.1: selection, projects, manual cut, listening at once, shortcuts ----------
    "Tick or untick every track: the global buttons only process ticked tracks.":
        "Cocher ou décocher toutes les pistes : les boutons du bas ne traitent que les pistes cochées.",
    "📂 Open a project…":
        "📂 Ouvrir un projet…",
    "💾 Save the project…":
        "💾 Enregistrer le projet…",
    "Reopen a session saved as a .htd file (Ctrl+O / ⌘O).":
        "Rouvrir une session enregistrée dans un fichier .htd (Ctrl+O / ⌘O).",
    "Save the whole session in a .htd file: tracks, ticks, titles, BPM, keys, cuts, A-B markers, modes and the settings on the left (Ctrl+S / ⌘S).":
        "Enregistre toute la session dans un fichier .htd : pistes, coches, titres, BPM, tonalités, coupes, marqueurs A-B, modes et réglages du panneau gauche (Ctrl+S / ⌘S).",
    "Writes the files of every ticked track (tracks not rendered with the current settings are rendered first).":
        "Écrit les fichiers de toutes les pistes cochées (celles qui ne sont pas encore calculées avec les réglages actuels le sont d'abord).",
    "Renders each ticked track with the current settings into a temporary folder so you can listen and compare. Nothing is written next to your files.":
        "Calcule chaque piste cochée avec les réglages actuels dans un dossier temporaire pour écouter et comparer. Rien n'est écrit à côté de vos fichiers.",
    "Project saved: {name}":
        "Projet enregistré : {name}",
    "Project opened: {name}":
        "Projet ouvert : {name}",
    "☑ Tick all":
        "☑ Tout cocher",
    "☐ Untick all":
        "☐ Tout décocher",
    "Tick at least one track":
        "Cochez au moins une piste",
    "Save the project":
        "Enregistrer le projet",
    "Heins True Diyae projects (*.htd)":
        "Projets Heins True Diyae (*.htd)",
    "Open a project":
        "Ouvrir un projet",
    "Replace the current list with this project?":
        "Remplacer la liste actuelle par ce projet ?",
    "cut {start} → {end}":
        "coupe {start} → {end}",
    "{n} ticked":
        "{n} cochée(s)",
    "The project could not be saved:\n{error}":
        "Le projet n'a pas pu être enregistré :\n{error}",
    "Saved in the project, not rendered yet: click to use these settings.":
        "Enregistré dans le projet, pas encore calculé : cliquez pour reprendre ces réglages.",
    "My project":
        "Mon projet",
    "This file is not a Heins True Diyae project:\n{path}":
        "Ce fichier n'est pas un projet Heins True Diyae :\n{path}",
    "{n} file of the project was not found (moved or deleted):":
        "{n} fichier du projet est introuvable (déplacé ou supprimé) :",
    "{n} files of the project were not found (moved or deleted):":
        "{n} fichiers du projet sont introuvables (déplacés ou supprimés) :",
    "Ticked tracks are the ones Prepare the previews and Export all work on.":
        "Les pistes cochées sont celles que traitent « Préparer l'écoute » et « Tout exporter ».",
    "✂ Cut":
        "✂ Coupe",
    "✂ Trim to A–B":
        "✂ Rogner sur A–B",
    "Keep only the part between the A and B markers.":
        "Ne garder que la partie entre les marqueurs A et B.",
    "Reset the cut":
        "Réinitialiser la coupe",
    "Keep the whole track again.":
        "Reprendre la piste entière.",
    "Listen to the original now; prepare the previews to hear the master and export.":
        "Écoutez l'original dès maintenant ; préparez l'écoute pour entendre le master et exporter.",
    "Start of the part kept (m:ss.mmm). The source file is never modified.":
        "Début de la partie gardée (m:ss.mmm). Le fichier source n'est jamais modifié.",
    "End of the part kept (m:ss.mmm). The source file is never modified.":
        "Fin de la partie gardée (m:ss.mmm). Le fichier source n'est jamais modifié.",
    "Original or Master: switching keeps the same moment":
        "Original ou Master : la bascule garde le même moment",
    "{length} kept":
        "{length} gardés",
    "Prepare the previews to export.":
        "Préparez l'écoute pour exporter.",
    "✂ Manual cut {start} → {end} ({length})":
        "✂ Coupe manuelle {start} → {end} ({length})",
    "whole track":
        "piste entière",
    "This file cannot be played: {error}":
        "Ce fichier ne peut pas être lu : {error}",
    "Back to A (or to the start when there is no loop)":
        "Retour à A (ou au début sans boucle)",
    "Space":
        "Espace",
    "The cut keeps less than half a second.":
        "La coupe garde moins d'une demi-seconde.",
    # ---- v2.2: pause, per-track mode, help / about, shortcuts, signature ----------
    "by":
        "par",
    "⏸ Pause":
        "⏸ Pause",
    "▶ Resume":
        "▶ Reprendre",
    "Queue paused - the current track finishes, then it waits.":
        "File en pause - la piste en cours se termine, puis l'attente commence.",
    "Pause the queue after the current track (the work already done is kept).":
        "Mettre la file en pause après la piste en cours (le travail déjà fait est gardé).",
    "Pause the queue after the current file (the work already done is kept).":
        "Mettre la file en pause après le fichier en cours (le travail déjà fait est gardé).",
    "Follow the left panel":
        "Suivre le panneau gauche",
    "Profile: {name}":
        "Profil : {name}",
    "Mode for this track: follow the left panel, or a preset / profile just for it. Lets you queue several tracks with different modes at once.":
        "Mode de cette piste : suivre le panneau gauche, ou un preset / profil rien que pour elle. Permet de préparer plusieurs pistes avec des modes différents d'un coup.",
    "Save the changes to the project before quitting?":
        "Enregistrer les modifications du projet avant de quitter ?",
    "Untitled project":
        "Projet sans titre",
    "Shortcuts, licence and logs":
        "Raccourcis, licence et journaux",
    "Help & About - {app}":
        "Aide et à propos - {app}",
    "Shortcuts":
        "Raccourcis",
    "Licence":
        "Licence",
    "Close":
        "Fermer",
    "Open the logs folder":
        "Ouvrir le dossier des journaux",
    "Attach {file} to a bug report.":
        "Joignez {file} à un signalement de bug.",
    "Open the full notices (THIRD_PARTY_NOTICES.md)":
        "Ouvrir les notices complètes (THIRD_PARTY_NOTICES.md)",
    "Keyboard shortcuts (disabled while typing in a field):":
        "Raccourcis clavier (désactivés pendant la saisie dans un champ) :",
    "Switch Original / Master (same moment)":
        "Basculer Original / Master (même moment)",
    "Mono on / off":
        "Mono activé / désactivé",
    "Loop on / off":
        "Boucle activée / désactivée",
    "Set the loop start / end at the current moment":
        "Placer le début / la fin de boucle à l'instant présent",
    "Move 5 seconds back / forward":
        "Reculer / avancer de 5 secondes",
    "Undo / redo (ticks, cuts, modes, titles, track list)":
        "Annuler / rétablir (coches, coupes, modes, titres, liste des pistes)",
    "Save / open a project (.htd)":
        "Enregistrer / ouvrir un projet (.htd)",
    "This window":
        "Cette fenêtre",
    "Heins True Diyae Pro is free software under the GNU General Public License v3 (GPL-3.0), because its mastering chain uses pedalboard (GPL-3.0). You may use, study, share and modify it; if you distribute it, share the source under the same licence.":
        "Heins True Diyae Pro est un logiciel libre sous licence GNU General Public License v3 (GPL-3.0), car sa chaîne de mastering utilise pedalboard (GPL-3.0). Vous pouvez l'utiliser, l'étudier, le partager et le modifier ; si vous le distribuez, partagez le code source sous la même licence.",
    "It also builds on PySide6/Qt (LGPL-3.0), NumPy, SciPy, librosa, soundfile, pyloudnorm, Matplotlib, Pillow, sounddevice/PortAudio and FFmpeg. The full list and the FFmpeg source offer are in THIRD_PARTY_NOTICES.md next to the app.":
        "Il s'appuie aussi sur PySide6/Qt (LGPL-3.0), NumPy, SciPy, librosa, soundfile, pyloudnorm, Matplotlib, Pillow, sounddevice/PortAudio et FFmpeg. La liste complète et l'offre de sources FFmpeg figurent dans THIRD_PARTY_NOTICES.md à côté de l'application.",
}

# Engine messages that carry numbers or names: (regular expression, French template).
# Named groups starting with "msg" are translated recursively.
FR_ENGINE_PATTERNS = [
    (r"Mastering: EQ and compression \((?P<name>.+)\)", "Mastering : EQ et compression ({name})"),
    (r"(?P<msg>Original|Cleaned|Mastered) \(dBFS RMS\)", "{msg} (dBFS RMS)"),
    (r"Loudness landed at (?P<got>-?[\d.]+) LUFS instead of (?P<want>-?[\d.]+) LUFS: this material cannot "
     r"reach the target under the true-peak ceiling without excessive limiting\.",
     "Le volume est arrivé à {got} LUFS au lieu de {want} LUFS : ce morceau ne peut pas atteindre la cible "
     "sous le plafond true peak sans limitation excessive."),
    (r"The limiter had to remove up to (?P<db>[\d.]+) dB on the loudest peaks to reach this target\. If it "
     r"sounds squashed, pick a quieter profile\.",
     "Le limiteur a dû retirer jusqu'à {db} dB sur les crêtes les plus fortes pour atteindre cette cible. "
     "Si ça sonne écrasé, choisis un profil moins fort."),
    (r"Resampled (?P<a>[\d,]+) Hz -> (?P<b>[\d,]+) Hz\.", "Rééchantillonné de {a} Hz à {b} Hz."),
    (r"(?P<n>\d+) channels found - only the first two \(L/R\) are used\.",
     "{n} canaux trouvés : seuls les deux premiers (G/D) sont utilisés."),
    (r"Source peaks exceed full scale by (?P<db>[\d.]+) dB \(floating-point file\)\.",
     "Les crêtes de la source dépassent la pleine échelle de {db} dB (fichier en virgule flottante)."),
    (r"This file could not be decoded - it may be corrupt or not a real \.(?P<ext>\w+) file\.(?P<rest>.*)",
     "Ce fichier n'a pas pu être décodé : il est peut-être corrompu ou n'est pas un vrai fichier .{ext}.{rest}"),
    (r"Unsupported file type '\.(?P<ext>[^']*)'\. Accepted formats: (?P<list>.*)\.",
     "Type de fichier non pris en charge (.{ext}). Formats acceptés : {list}."),
    (r"The file is larger than the (?P<mb>\d+) MB limit\.", "Le fichier dépasse la limite de {mb} Mo."),
    (r"Unsupported sample rate \((?P<sr>\d+) Hz\)\. Accepted range: (?P<range>.*) Hz\.",
     "Fréquence d'échantillonnage non prise en charge ({sr} Hz). Plage acceptée : {range} Hz."),
    (r"The track is too short \((?P<s>[\d.]+) s\)\. Minimum length: (?P<min>[\d.]+) s\.",
     "La piste est trop courte ({s} s). Durée minimale : {min} s."),
    (r"The track is longer than the (?P<min>\d+)-minute limit\.", "La piste dépasse la limite de {min} minutes."),
    (r"Sample-rate conversion (?P<a>\d+) Hz -> (?P<b>\d+) Hz failed \((?P<detail>.*)\)\.",
     "La conversion de {a} Hz à {b} Hz a échoué ({detail})."),
    (r"Band-limiting filters failed \((?P<detail>.*)\)\.", "Les filtres de limitation de bande ont échoué ({detail})."),
    (r"The effects chain failed \((?P<detail>.*)\)\.", "La chaîne d'effets a échoué ({detail})."),
    (r"The cover image was not found: (?P<path>.*)", "Image de pochette introuvable : {path}"),
    (r"The cover image could not be read \((?P<detail>.*)\)\.", "L'image de pochette est illisible ({detail})."),
    (r"FFmpeg could not encode the file: (?P<detail>.*)", "FFmpeg n'a pas pu encoder le fichier : {detail}"),
    (r"FFmpeg could not (?P<msgwhat>encode the clip|make the video|write the tags): (?P<detail>.*)",
     "FFmpeg n'a pas pu {msgwhat} : {detail}"),
    (r"Could not find a free file name next to (?P<path>.*)\.", "Aucun nom de fichier libre à côté de {path}."),
    (r"(?P<msglabel>.+) export needs FFmpeg, which was not found\.",
     "L'export {msglabel} a besoin de FFmpeg, qui est introuvable."),
    (r"Export failed: (?P<detail>.*)", "Échec de l'export : {detail}"),
    (r"Unexpected error: (?P<detail>.*)", "Erreur inattendue : {detail}"),
    (r"FFmpeg exit code (?P<code>-?\d+)", "Code de sortie FFmpeg {code}"),
]


def _french_spacing(text: str) -> str:
    """Non-breaking space before : ; ? ! (French typography; never breaks a line there)."""
    for mark in (":", ";", "?", "!"):
        text = text.replace(f" {mark}", f" {mark}")
    return text


FR = {source: _french_spacing(target) for source, target in FR.items()}
FR_ENGINE_PATTERNS = [(pattern, _french_spacing(template)) for pattern, template in FR_ENGINE_PATTERNS]
