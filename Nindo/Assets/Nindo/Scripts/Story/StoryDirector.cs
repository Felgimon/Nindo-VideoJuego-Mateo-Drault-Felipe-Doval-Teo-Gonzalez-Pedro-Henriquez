using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Guion del juego (según el documento de diseño): prólogo con la guadaña y la bandana,
    /// tutorial de parry en cámara lenta, el rastro hasta la muralla, el jardín del clan, el
    /// luchador de sumo (tutorial del dash mágico), los tres guardianes de los sellos, la
    /// puerta del dojo y el combate final contra Kage para rescatar al abuelo.
    /// </summary>
    public class StoryDirector : MonoBehaviour
    {
        PlayerController P => Game.Player;
        bool parryTutorial, finisherTip;
        GameObject scytheProp;
        Coroutine deathRoutine;

        void Awake()
        {
            Game.Story = this;
        }

        void OnEnable()
        {
            GameEvents.PlayerDied += OnPlayerDied;
            GameEvents.BossDefeated += OnBossDefeated;
            GameEvents.FlagSet += OnFlag;
            GameEvents.Parry += OnParry;
        }

        void OnDisable()
        {
            GameEvents.PlayerDied -= OnPlayerDied;
            GameEvents.BossDefeated -= OnBossDefeated;
            GameEvents.FlagSet -= OnFlag;
            GameEvents.Parry -= OnParry;
        }

        void OnDestroy() { if (Game.Story == this) Game.Story = null; }

        // ================================================================== inicio
        public void Begin(bool newGame)
        {
            var s = Game.Save;
            P.SetKatanaVisible(s.HasFlag(Flags.KatanaObtained));
            UpdateObjective();
            if (!s.HasFlag(Flags.IntroDone)) StartCoroutine(Intro());
            else
            {
                StartCoroutine(Game.UI.Fade(0f, 1.2f));
                Zone.ForceRefresh();
            }
        }

        public void UpdateObjective() => Game.UI?.SetObjective(StoryText.Objective(Game.Save));

        // ================================================================== cinemáticas
        IEnumerator Cutscene(IEnumerator body, bool letterbox = true)
        {
            // si justo estaba en pausa (p. ej. Esc durante la cámara lenta de la muerte de un jefe) la
            // cinemática espera: si no, corría detrás del panel y el diálogo avanzaba con los clics del menú
            while (Game.IsPaused) yield return null;
            Game.InCutscene = true;
            if (Game.Input != null) Game.Input.GameplayBlocked = true;
            if (letterbox) Game.UI?.Letterbox(true);
            P?.EnterScripted();
            yield return body;
            if (letterbox) Game.UI?.Letterbox(false);
            Game.Camera?.CancelAllShots();
            P?.ExitScripted();
            Game.InCutscene = false;
            if (Game.Input != null) { Game.Input.GameplayBlocked = Game.IsPaused; Game.Input.ClearBuffer(); }
            UpdateObjective();
        }

        IEnumerator Say(string id) => Game.UI.Dialogue(StoryText.Dialogue(id));

        public void PlayDialogueById(string id) => StartCoroutine(Cutscene(Say(id), false));

        Vector3 PointPos(string id, Vector3 fallback)
        {
            var t = Game.World != null ? Game.World.Point(id) : null;
            return t != null ? t.position : fallback;
        }

        // ================================================================== PRÓLOGO
        IEnumerator Intro()
        {
            while (Game.IsPaused) yield return null;   // pausa abierta durante la carga
            Game.InCutscene = true;
            if (Game.Input != null) Game.Input.GameplayBlocked = true;
            Game.UI.SetFade(1f);
            Game.UI.Letterbox(true);
            P.EnterScripted();
            P.SetKatanaVisible(false);

            // el ninja que se queda espera quieto
            var introEnc = Encounter.Get("intro");
            if (introEnc != null)
            {
                introEnc.manualActivation = true;
                foreach (var m in introEnc.Members) if (m != null) m.EnterScripted();
            }

            // la guadaña tirada en el piso
            Vector3 scythePos = PointPos("scythe", P.transform.position + P.transform.forward * 1.6f);
            scytheProp = new GameObject("Guadaña");
            scytheProp.transform.position = scythePos;
            var model = Game.Content.Prop("scythe");
            if (model != null) Instantiate(model, scytheProp.transform);
            var bandana = scytheProp.AddComponent<BandanaScythe>();
            bandana.prompt = "Desatar la cinta";
            bandana.promptHeight = 1f;
            bandana.radius = 2.5f;
            bandana.enabled = false;

            // abuelo y su secuestrador (animación "inicio" del equipo: el ninja lo tacklea y lo arrastra)
            Vector3 kidPos = PointPos("kidnap_a", P.transform.position + new Vector3(6, 0, 8));
            Vector3 exit = PointPos("kidnap_exit", kidPos + new Vector3(0, 0, 25));
            var grandpa = NPC.Spawn("kidnap", kidPos, Quaternion.LookRotation((P.transform.position - kidPos).Flat().normalized + Vector3.forward * 0.001f), null);
            grandpa.Play("Idle", 0f);
            Enemy kidnapper = null;

            // texto de apertura sobre negro
            yield return new WaitForSecondsRealtime(0.6f);
            Game.UI.ShowAreaTitle("Una noche de luna llena", "Kaito y su abuelo escucharon un ruido en los cultivos...");
            yield return new WaitForSecondsRealtime(4.4f);
            Game.UI.ShowAreaTitle("...", "Kaito salió con la guadaña. De un arbusto salió un golpe.");
            Game.Audio?.Play("hit_heavy", null, 1f);
            Game.Camera?.Shake(0.6f);
            yield return new WaitForSecondsRealtime(4.2f);

            // Kaito tirado en el piso
            var lie = StartCoroutine(LieDown(true));
            int shot = Game.Camera.PlayFollowShot(P.transform, new Vector3(2.2f, 2.2f, 2.6f), 0.3f, 32f, 0f, 0f, 1f, false);
            yield return Game.UI.Fade(0f, 2.5f);
            yield return new WaitForSecondsRealtime(0.8f);
            yield return LieDown(false);
            Game.Camera.CancelShot(shot);

            // ve al abuelo siendo llevado
            int shot2 = Game.Camera.PlayFollowShot(grandpa.transform, new Vector3(-3.5f, 3.2f, -6f), 1.0f, 32f, 0f, 0.9f, 0.9f, false);
            grandpa.Play("Kidnap", 0.1f);
            Game.Audio?.Play("hit_heavy", grandpa.transform.position, 0.8f);
            yield return new WaitForSecondsRealtime(2.4f);
            yield return Say("intro_wake");
            Game.Camera.CancelShot(shot2);
            // lo arrastran lentamente hacia el bosque
            grandpa.FaceTo(grandpa.transform.position - (exit - grandpa.transform.position));
            grandpa.SlideTo(exit, 1.1f);

            // control al jugador: tiene que desatar la cinta
            Game.UI.Letterbox(false);
            P.ExitScripted();
            Game.InCutscene = false;
            if (Game.Input != null) Game.Input.GameplayBlocked = false;
            bandana.enabled = true;
            UpdateObjective();
            Game.UI.ShowTutorial($"Acercate a la guadaña y presioná {{Interact}}");
            while (!Game.Save.HasFlag(Flags.KatanaObtained)) yield return null;
            Game.UI.HideTutorial();

            // ¡la bandana se ata sola y la guadaña se vuelve katana!
            yield return Cutscene(BandanaAwakening(grandpa, kidnapper));

            // pelea del prólogo con tutorial de parry. Si el guardado ya tiene el encuentro ganado
            // pero no "intro_done" (se salió durante el diálogo final), Activate() no haría nada y
            // FinishIntro no se llamaría nunca: el prólogo se repetiría en cada "Continuar".
            if (introEnc != null && !introEnc.Completed)
            {
                // el ninja de la práctica no muere ni se quiebra hasta que se practique a velocidad real
                foreach (var m in introEnc.Members) if (m != null) { m.ExitScripted(true); m.SetParryPractice(true); }
                introEnc.Activate();
                parryTutorial = true;
                parryGuided = parryRealtime = parryMisses = parryAttempts = 0;
            }
            else FinishIntro();
        }

        IEnumerator LieDown(bool down)
        {
            // el pivote del modelo (LeanPivot) lo reescribe ProceduralMotion en cada LateUpdate:
            // la pose se le pasa a él en vez de rotar el pivote directo (si no, Kaito nunca se acuesta)
            var motion = P.GetComponent<ProceduralMotion>();
            if (motion == null) yield break;
            Quaternion lying = Quaternion.Euler(-82f, 0f, 0f);
            if (down) { motion.scriptedPose = lying; yield break; }
            float t = 0f;
            while (t < 1f)
            {
                t += Time.unscaledDeltaTime * 1.4f;
                motion.scriptedPose = Quaternion.Slerp(lying, Quaternion.identity, Mathf.SmoothStep(0f, 1f, t));
                yield return null;
            }
            motion.scriptedPose = Quaternion.identity;
        }

        IEnumerator BandanaAwakening(NPC grandpa, Enemy kidnapper)
        {
            P.ScriptedFace(scytheProp.transform.position);
            int shot = Game.Camera.PlayAbilityShot(P.transform, CameraDirector.AbilityShot.LowOrbit, 3.2f);
            Game.Time.SlowMotion(0.4f, 1.6f, 0.1f, 0.5f);
            Game.FX.SealGlow(P.transform.position + Vector3.up);
            Game.FX.Petals(P.transform.position + Vector3.up, 1.5f);
            Game.Audio?.Play("rage_on", P.transform.position, 1f);
            Destroy(scytheProp);
            yield return new WaitForSecondsRealtime(0.9f);
            P.SetKatanaVisible(true);
            P.ScriptedPlay("Attack3");
            Game.FX.Screen.WhiteFlash(0.7f);
            Game.Camera.Shake(0.5f);
            Game.UI.ShowToast("Espíritu de la Bandana", UIFactory.Gold, 2.2f);
            yield return new WaitForSecondsRealtime(1.6f);
            Game.Camera.CancelShot(shot);
            yield return Say("intro_bandana");
            // el secuestrador se lleva al abuelo entre el humo
            if (grandpa != null) { Game.FX.SmokePuff(grandpa.transform.position + Vector3.up, 1.6f); Destroy(grandpa.gameObject); }
            if (kidnapper != null) Destroy(kidnapper.gameObject);
            Game.Audio?.Play("teleport", P.transform.position, 0.8f);
            P.AddSpirit(60f);
        }

        void FinishIntro()
        {
            StartCoroutine(Cutscene(IntroOutro()));
        }

        IEnumerator IntroOutro()
        {
            parryTutorial = false;
            EndParryWatch();
            Game.UI.HideTutorial();   // el texto de la práctica no puede quedar encima del diálogo
            P.RestoreAll();
            yield return Say("intro_after_fight");
            Game.Save.SetFlag(Flags.IntroDone);
            var cp = Checkpoint.Get("cp_home");
            if (cp != null) cp.Activate(P, false);
            SaveSystem.Save();
            Game.UI.ShowTutorial($"Tip: {{Lock}} fija a un enemigo. Mantenelo apretado para soltarlo.");
            StartCoroutine(HideTutorialLater(5f));
        }

        IEnumerator HideTutorialLater(float s) { yield return new WaitForSecondsRealtime(s); Game.UI.HideTutorial(); }

        // ================================================================== tutoriales
        // Enseñan la pista que se ve a velocidad normal: el anillo (ensō) que se cierra alrededor del atacante.
        // Parry: primero guiado en cámara lenta (el anillo dorado se cierra despacio y se aprieta al cerrarse),
        // después a velocidad real; si falla dos seguidas, una ayuda a 0.6x. Mientras dura, el ninja está en modo
        // práctica (Enemy.SetParryPractice); si falla muchas seguidas igual se termina, para no trabar el prólogo.
        // Dash: con el sumo (un común), nunca congelando una pelea de jefe.
        const int GuidedParries = 2, RealtimeParries = 2, MaxGuidedAttempts = 4, MaxPracticeMisses = 8;
        int tutorialSlow = -1;
        int parryGuided, parryRealtime, parryMisses, parryAttempts;
        Enemy parryWatch, dashWatch;
        int parryWatchTell, dashWatchTell;
        bool parryWatching, parryLanded, waitingDash;

        bool ParryGuidedPhase => parryGuided < GuidedParries && parryAttempts < MaxGuidedAttempts;

        void Update()
        {
            if (P == null || Game.IsPaused) return;
            if (parryTutorial || parryWatching) TickParryTutorial();
            TickDashTutorial();

            // primer enemigo desequilibrado: explicar la ejecución
            if (!finisherTip && P.FinisherCandidate() != null && !Game.Save.HasFlag("tip_finisher"))
            {
                finisherTip = true;
                Game.Save.SetFlag("tip_finisher");
                Game.Time.SlowMotion(0.25f, 1.2f, 0.05f, 0.4f);
                Game.UI.ShowTutorial($"¡Está desequilibrado! Pegale {{Attack}} o EJECUTALO con {{Finisher}} (cuesta Espíritu, te cura)");
                StartCoroutine(HideTutorialLater(4.5f));
            }
        }

        void TickParryTutorial()
        {
            if (parryWatching)
            {
                // el golpe salió (lo desvió o no) o se cortó: fuera la cámara lenta y se cuenta
                bool over = !parryTutorial || Game.InCutscene || parryWatch == null || !parryWatch.InTell || parryWatch.TellId != parryWatchTell;
                if (!over) return;
                bool guided = ParryGuidedPhase;
                EndParryWatch();
                if (!parryTutorial) return;
                if (parryLanded) { if (guided) parryGuided++; else parryRealtime++; parryMisses = 0; }
                else parryMisses++;
                if (guided) parryAttempts++;
                if (parryRealtime >= RealtimeParries || parryMisses >= MaxPracticeMisses) { FinishParryTutorial(); return; }
                // el primer parry: qué se ganó (queda hasta el próximo golpe, mientras el ninja está abierto)
                if (parryLanded && guided && parryGuided == 1)
                {
                    Game.UI.ShowTutorial("Cada parry DESEQUILIBRA al enemigo: cuando termina su ataque queda abierto. ¡Castigalo!");
                    return;
                }
                ShowParryText(false);
                return;
            }
            if (Game.InCutscene) return;
            var enc = Encounter.Get("intro");
            if (enc == null) return;
            foreach (var e in enc.Members)
                // solo con un golpe desviable que de verdad llega (zona/alcance real): si no, se enseña mal
                if (e != null && e.IsAlive && e.InTell && e.StepKind != AttackKind.Unblockable && e.StrikeCanReach(P.transform.position, P.Radius + 0.3f))
                {
                    parryWatching = true;
                    parryLanded = false;
                    parryWatch = e;
                    parryWatchTell = e.TellId;
                    bool assist = !ParryGuidedPhase && parryMisses >= 2;
                    if (ParryGuidedPhase)
                    {
                        // se congela un segundo al aparecer el anillo (para leer) y sigue en cámara lenta: el anillo
                        // se ve cerrarse despacio y se aprieta en el cierre, igual que después a velocidad real
                        Game.Time.SlowMotion(0.03f, 1f, 0.05f, 0.3f);
                        tutorialSlow = Game.Time.SlowMotion(0.2f, 30f, 0.05f, 0.1f);
                    }
                    else if (assist) tutorialSlow = Game.Time.SlowMotion(0.6f, 30f, 0.05f, 0.1f);
                    ShowParryText(true);
                    break;
                }
        }

        void ShowParryText(bool attacking)
        {
            const string k = "{Parry}";   // la UI la dibuja con la tecla del dispositivo de ese momento
            if (ParryGuidedPhase)
            {
                if (attacking)
                    Game.UI.ShowTutorial(parryMisses > 0
                        ? $"Esperá a que el anillo dorado se cierre del todo y recién ahí presioná {k}"
                        : $"Mirá el anillo dorado: cuando se cierre, presioná {k} (Parry)");
                else Game.UI.HideTutorial();
                return;
            }
            // práctica a velocidad real: el texto queda hasta lograrlo
            Game.UI.ShowTutorial($"Ahora a velocidad real: {k} justo cuando se cierra el anillo dorado  ({parryRealtime}/{RealtimeParries})");
        }

        void EndParryWatch()
        {
            parryWatching = false;
            parryWatch = null;
            if (tutorialSlow >= 0) { Game.Time.CancelSlowMotion(tutorialSlow); tutorialSlow = -1; }
        }

        void FinishParryTutorial()
        {
            parryTutorial = false;
            Game.Save.SetFlag("tip_parry_done");
            var enc = Encounter.Get("intro");
            if (enc != null) foreach (var m in enc.Members) if (m != null) m.SetParryPractice(false);
            Game.UI.ShowTutorial("Parry cuando se cierra el anillo dorado y, cuando quede abierto, castigalo. ¡Terminá la pelea!");
            StartCoroutine(HideTutorialLater(4.5f));
        }

        void TickDashTutorial()
        {
            if (waitingDash)
            {
                // la cámara lenta sigue hasta que sale el golpe (no se corta al apretar: el dash también se ve lento)
                bool over = Game.InCutscene || dashWatch == null || !dashWatch.InTell || dashWatch.TellId != dashWatchTell;
                if (!over) return;
                waitingDash = false;
                dashWatch = null;
                if (tutorialSlow >= 0) { Game.Time.CancelSlowMotion(tutorialSlow); tutorialSlow = -1; }
                Game.UI.HideTutorial();
                return;
            }
            if (Game.Save.HasFlag(Flags.DashUnlocked) || Game.InCutscene || Game.Combat == null) return;
            foreach (var e in Game.Combat.Engaged)
            {
                // solo imparables que pueden conectar (carril hacia Kaito, Kaito dentro del pisotón)
                if (e == null || !e.InTell || e.StepKind != AttackKind.Unblockable || !e.StrikeCanReach(P.transform.position, P.Radius)) continue;
                const string k = "{Dash}";
                if (e is Boss)
                {
                    // pelea de jefe sin el dash todavía: se habilita sin congelar la pelea
                    Game.Save.SetFlag(Flags.DashUnlocked);
                    P.AddSpirit(40f);
                    Game.UI.ShowTutorial($"Anillo ROJO: no se puede desviar. Esquivá con {k} cuando se cierre (DASH MÁGICO)");
                    StartCoroutine(HideTutorialLater(4f));
                    return;
                }
                // con el sumo, igual que el parry guiado: se congela un segundo al aparecer el anillo rojo (para leer) y
                // sigue en cámara lenta hasta el golpe. Antes arrancaba con el anillo casi cerrado y se cortaba al
                // apretar: el que apretaba al terminar de leer esquivaba antes de tiempo y comía la embestida
                Game.Save.SetFlag(Flags.DashUnlocked);
                P.AddSpirit(40f);
                waitingDash = true;
                dashWatch = e;
                dashWatchTell = e.TellId;
                Game.Time.SlowMotion(0.03f, 1f, 0.05f, 0.3f);
                tutorialSlow = Game.Time.SlowMotion(0.2f, 30f, 0.05f, 0.1f);
                Game.UI.ShowTutorial($"¡Anillo ROJO: no se puede desviar! Esquivá hacia un costado con {k} cuando se cierre (DASH MÁGICO, usa Espíritu)");
                return;
            }
        }

        void OnParry(bool perfect)
        {
            if (!parryWatching) return;
            parryLanded = true;
            Game.UI.ShowCallout(perfect ? "¡Parry perfecto!" : "¡Parry!", UIFactory.Gold);
        }

        // ================================================================== triggers del mapa
        public void OnTrigger(string id, StoryTrigger t)
        {
            if (!id.StartsWith("enc_done_")) Game.Save.SetFlag("trig_" + id);
            switch (id)
            {
                case "enc_done_intro": FinishIntro(); break;
                case "fields": StartCoroutine(Cutscene(Say("fields"), false)); break;
                case "forest_reveal": StartCoroutine(Cutscene(ForestReveal())); break;
                case "wall_guards":
                    StartCoroutine(Cutscene(Say("wall_guards"), false));
                    break;
                case "enc_done_wall": StartCoroutine(Cutscene(WallOpens())); break;
                case "garden": StartCoroutine(Cutscene(Say("garden"), false)); break;
                case "sumo_intro":
                {
                    // si el sumo ya cayó (se entró por el costado y se peleó antes del disparador) no hay
                    // provocación que mostrar: solo se asegura que el encuentro esté activo
                    var enc = Encounter.Get("sumo");
                    bool liveSumo = false;
                    if (enc != null) foreach (var m in enc.Members) if (m != null && m.IsAlive && m.config.id.StartsWith("sumo")) liveSumo = true;
                    if (liveSumo) StartCoroutine(Cutscene(SumoIntro()));
                    else enc?.Activate();
                    break;
                }
                case "enc_done_sumo": StartCoroutine(Cutscene(AbilitiesUnlock())); break;
                case "dojo_gate":
                    Game.Save.SetFlag(Flags.DojoGateSeen);
                    StartCoroutine(Cutscene(DojoGateFirstLook()));
                    break;
            }
            UpdateObjective();
        }

        IEnumerator ForestReveal()
        {
            Vector3 a = PointPos("forest_kidnap_a", P.transform.position + new Vector3(0, 0, 18));
            Vector3 b = PointPos("forest_kidnap_b", a + new Vector3(0, 0, 14));
            // el ninja arrastra al abuelo (último frame de la animación del secuestro)
            var grandpa = NPC.Spawn("kidnap", a, Quaternion.LookRotation(-(b - a).Flat().normalized + Vector3.forward * 0.001f), null);
            grandpa.Play("Kidnap", 0f);
            grandpa.SkipToEnd();
            yield return null;
            grandpa.SlideTo(b, 1.3f);
            int shot = Game.Camera.PlayFollowShot(grandpa.transform, new Vector3(-5f, 4.5f, -7f), 1f, 34f, 0f, 1.2f, 1.2f, false);
            yield return new WaitForSecondsRealtime(1.5f);
            yield return Say("forest_reveal");
            yield return new WaitForSecondsRealtime(1.2f);
            Game.FX.SmokePuff(grandpa.transform.position + Vector3.up, 1.5f);
            Destroy(grandpa.gameObject);
            Game.Camera.CancelShot(shot);
            Game.Save.SetFlag(Flags.ForestSeen);
        }

        IEnumerator WallOpens()
        {
            Game.Save.SetFlag(Flags.WallGateOpen);
            Vector3 gate = PointPos("wall_gate", P.transform.position + P.transform.forward * 8f);
            int shot = Game.Camera.PlayStaticShot(gate + new Vector3(4f, 6f, -12f), gate + Vector3.up * 2f, 34f, 3.2f, 1f, 1f);
            yield return new WaitForSecondsRealtime(3.4f);
            yield return Say("wall_open");
            Game.Camera.CancelShot(shot);
        }

        IEnumerator SumoIntro()
        {
            var enc = Encounter.Get("sumo");
            Enemy sumo = null;
            if (enc != null) foreach (var m in enc.Members) if (m != null && m.IsAlive && m.config.id.StartsWith("sumo")) sumo = m;
            int shot = -1;
            if (sumo != null)
            {
                sumo.EnterScripted();
                sumo.ScriptedFace(P.transform.position);
                sumo.ScriptedPlay("Spotted");
                shot = Game.Camera.PlayBossIntroShot(sumo.transform, 2.6f, 3.5f);
            }
            yield return new WaitForSecondsRealtime(1.2f);
            yield return Say("sumo_intro");
            if (shot >= 0) Game.Camera.CancelShot(shot);
            if (sumo != null) sumo.ExitScripted(true);
            enc?.Activate();
        }

        IEnumerator AbilitiesUnlock()
        {
            Game.Save.SetFlag(Flags.AbilitiesUnlocked);
            Game.Save.SetFlag(Flags.DashUnlocked);
            P.AddSpirit(100f);
            Game.FX.SealGlow(P.transform.position + Vector3.up);
            int shot = Game.Camera.PlayAbilityShot(P.transform, CameraDirector.AbilityShot.LowOrbit, 2.5f);
            yield return new WaitForSecondsRealtime(0.8f);
            yield return Say("abilities");
            Game.Camera.CancelShot(shot);
            Game.UI.ShowTutorial($"{{Ability1}} Corte del Viento (35)   ·   {{Ability2}} Torbellino de Hojas (30)");
            StartCoroutine(HideTutorialLater(6f));
        }

        IEnumerator DojoGateFirstLook()
        {
            var gate = Game.World.Point("seal_gate");
            int shot = -1;
            if (gate != null) shot = Game.Camera.PlayStaticShot(gate.position + gate.forward * -16f + Vector3.up * 7f, gate.position + Vector3.up * 5f, 36f, 6f, 1.2f, 1f);
            yield return new WaitForSecondsRealtime(1.4f);
            yield return Say("dojo_gate");
            if (shot >= 0) Game.Camera.CancelShot(shot);
        }

        // ================================================================== jefes
        public void BossIntro(BossArena arena)
        {
            StartCoroutine(Cutscene(BossIntroRoutine(arena)));
        }

        IEnumerator BossIntroRoutine(BossArena arena)
        {
            var b = arena.Boss;
            if (b == null) yield break;
            b.EnterScripted();
            b.ScriptedFace(P.transform.position);
            Game.Audio?.StopMusic(1.5f);
            int shot = Game.Camera.PlayBossIntroShot(b.transform, b.config.height * b.config.scale, 4f);
            yield return new WaitForSecondsRealtime(0.8f);
            b.ScriptedPlay(b.introAnim, 0.2f);
            Game.Audio?.Play("boss_roar", b.transform.position, 1f);
            Game.Camera.Shake(0.35f);
            Game.UI.ShowAreaTitle(b.title, b.subtitle);
            yield return new WaitForSecondsRealtime(2.6f);
            yield return Say(b.bossId + "_intro");
            Game.Camera.CancelShot(shot);
            yield return new WaitForSecondsRealtime(0.3f);
            b.ExitScripted(false);
            b.BeginFight();
        }

        void OnBossDefeated(Boss b)
        {
            foreach (var a in Game.World.Arenas) if (a.Boss == b) a.OnBossDefeated();
            if (b.bossId == "kage") StartCoroutine(Ending());
            else Game.UI?.ShowToast($"{b.title} derrotado", UIFactory.Gold, 2.5f);
            UpdateObjective();
        }

        public void OnSealObtained(SealId seal)
        {
            StartCoroutine(Cutscene(SealRoutine(seal), false));
        }

        IEnumerator SealRoutine(SealId seal)
        {
            string id = seal == SealId.Montana ? "seal_mountain" : seal == SealId.Lago ? "seal_lake" : "seal_bamboo";
            Game.UI.ShowSealObtained(seal);
            P.RestoreAll();
            yield return new WaitForSecondsRealtime(0.6f);
            yield return Say(id);
            if (Game.Save.SealCount >= 3) Game.UI.ShowToast("¡Los tres sellos! Volvé a la puerta del dojo", UIFactory.Gold, 3f);
            SaveSystem.Save();
        }

        public void OpenSealGate(SealGate gate)
        {
            if (Game.Save.SealCount < 3) { StartCoroutine(Cutscene(Say("dojo_gate_incomplete"), false)); return; }
            if (Game.Save.HasFlag(Flags.DojoOpen)) return;
            StartCoroutine(Cutscene(SealGateRoutine(gate)));
        }

        IEnumerator SealGateRoutine(SealGate gate)
        {
            // cámara frente al portón (forward del marcador = hacia afuera), mirando los huecos
            int shot = Game.Camera.PlayStaticShot(gate.transform.position + gate.transform.forward * 13f + Vector3.up * 4f, gate.SocketPosition(1), 34f, 7f, 1f, 1f);
            yield return new WaitForSecondsRealtime(1f);
            for (int i = 0; i < 3; i++) { gate.LightSocket(i); yield return new WaitForSecondsRealtime(0.8f); }
            Game.Camera.Shake(0.5f);
            Game.Save.SetFlag(Flags.DojoOpen);
            SaveSystem.Save();
            yield return new WaitForSecondsRealtime(2.2f);
            yield return Say("dojo_gate_open");
            Game.Camera.CancelShot(shot);
        }

        IEnumerator Ending()
        {
            Game.Save.SetFlag(Flags.FinalBossDone);
            SaveSystem.Save();
            yield return new WaitForSecondsRealtime(3.5f);
            yield return Cutscene(EndingScene());
            Game.Audio?.PlayMusic("ending", 3f);
            Game.UI.ShowEnding();
        }

        IEnumerator EndingScene()
        {
            var gp = Game.World.Point("npc_grandpa_dojo");
            NPC grandpa = gp != null ? gp.GetComponent<NPC>() : null;
            if (grandpa == null) grandpa = NPC.Spawn("grandpa", P.transform.position + P.transform.forward * 3f, Quaternion.identity, null);
            // la pelea con Kage puede terminar en cualquier punto del patio (36 m): si Kaito quedó lejos
            // del abuelo el plano del final mostraba el patio vacío. En negro se lo ubica al costado del
            // abuelo, perpendicular al plano de abajo (offset 3.5, -4.5), así se ven los dos de perfil.
            Vector3 camOff = new Vector3(3.5f, 0f, -4.5f).normalized;
            Vector3 dir = Vector3.Cross(Vector3.up, camOff);
            if (CombatMath.FlatDistance(P.transform.position, grandpa.transform.position + dir * 2.4f) > 1f)
            {
                yield return Game.UI.Fade(1f, 0.6f);
                Vector3 spot = grandpa.transform.position + dir * 2.4f;
                if (UnityEngine.AI.NavMesh.SamplePosition(spot, out var hit, 2f, UnityEngine.AI.NavMesh.AllAreas)) spot = hit.position;
                P.Teleport(spot, Quaternion.LookRotation(-dir));
                Game.Camera?.Snap();
                yield return Game.UI.Fade(0f, 0.8f);
            }
            grandpa.FaceTo(P.transform.position);
            P.ScriptedFace(grandpa.transform.position);
            Vector3 mid = (P.transform.position + grandpa.transform.position) * 0.5f;
            int shot = Game.Camera.PlayStaticShot(mid + new Vector3(3.5f, 2.6f, -4.5f), mid + Vector3.up * 1f, 34f, 0f, 1.5f, 1f);
            yield return new WaitForSecondsRealtime(1.5f);
            Game.FX.Petals(mid + Vector3.up * 2f, 2f);
            yield return Say("ending");
            Game.Camera.CancelShot(shot);
            Game.Save.SetFlag(Flags.Ending);
            SaveSystem.Save();
            yield return Game.UI.Fade(1f, 2f);
        }

        // ================================================================== muerte / viaje
        void OnPlayerDied()
        {
            if (deathRoutine != null) StopCoroutine(deathRoutine);
            deathRoutine = StartCoroutine(DeathRoutine());
        }

        IEnumerator DeathRoutine()
        {
            EndParryWatch();
            waitingDash = false; dashWatch = null;
            Game.UI.HideTutorial();
            Game.Audio?.PlayMusic("gameover", 1f, loop: false);
            yield return new WaitForSecondsRealtime(1.4f);
            yield return Game.UI.DeathScreen();
            Game.Time.ClearSlowMotion();
            Game.World.ResetAfterDeath();
            P.RespawnAt(Game.World.RespawnPoint(), Quaternion.identity);
            Zone.ForceRefresh();
            Game.Audio?.ResumeExplore(1.5f);
            yield return new WaitForSecondsRealtime(0.4f);
            yield return Game.UI.Fade(0f, 1.2f);
            deathRoutine = null;
        }

        public void TravelTo(string checkpointId, bool fx)
        {
            StartCoroutine(Cutscene(TravelRoutine(checkpointId, fx), false));
        }

        IEnumerator TravelRoutine(string id, bool fx)
        {
            if (fx) { Game.FX.PortalBurst(P.transform.position + Vector3.up); Game.Audio?.Play("portal", P.transform.position, 1f); }
            yield return Game.UI.Fade(1f, 0.7f);
            var cp = Checkpoint.Get(id);
            if (cp != null)
            {
                P.Teleport(cp.spawnPoint.position, cp.spawnPoint.rotation);
                cp.Activate(P, false);
            }
            Zone.ForceRefresh();
            yield return new WaitForSecondsRealtime(0.5f);
            yield return Game.UI.Fade(0f, 0.9f);
        }

        void OnFlag(string f)
        {
            if (f.StartsWith("boss_") || f == Flags.DojoOpen) UpdateObjective();
        }
    }

    /// <summary>La guadaña del abuelo: al desatar la cinta, Kaito obtiene la bandana y la katana.</summary>
    public class BandanaScythe : Interactable
    {
        public override void Interact(PlayerController p)
        {
            Game.Save.SetFlag(Flags.KatanaObtained);
            enabled = false;
        }
    }

    /// <summary>Puerta del dojo con los tres huecos para los sellos.</summary>
    /// <summary>
    /// Portón del dojo con los tres huecos para los sellos (modelados en dojo_gate). El marcador
    /// está en el centro del portón y su forward mira hacia afuera (hacia el jugador que llega).
    /// </summary>
    public class SealGate : Interactable
    {
        readonly GameObject[] sockets = new GameObject[3];
        // centro de cada hueco en coordenadas locales del portón (ver build_dojo_gate: x ±1.15,
        // altura 4.5+0.57, cara frontal en z 1.59); el medallón tiene el origen en su base (-0.25)
        static readonly Vector3[] offsets = { new Vector3(-1.15f, 4.82f, 1.64f), new Vector3(0f, 4.82f, 1.64f), new Vector3(1.15f, 4.82f, 1.64f) };
        static readonly string[] sealProps = { "key_seal_mountain", "key_seal_lake", "key_seal_bamboo" };

        void Awake()
        {
            prompt = "Colocar los sellos";
            radius = 4.5f;
            promptHeight = 2.2f;
        }

        void Start()
        {
            if (Game.Save.HasFlag(Flags.DojoOpen))
                for (int i = 0; i < 3; i++) Place(i);
        }

        public override bool CanInteract => !Game.Save.HasFlag(Flags.DojoOpen);

        public override void Interact(PlayerController p) => Game.Story?.OpenSealGate(this);

        /// <summary>Punto donde va el sello i (en el mundo).</summary>
        public Vector3 SocketPosition(int i) => transform.TransformPoint(offsets[i] + Vector3.up * 0.25f);

        GameObject Place(int i)
        {
            if (sockets[i] != null) return sockets[i];
            GameObject go;
            var model = Game.Content != null ? Game.Content.Prop(sealProps[i]) : null;
            if (model != null) go = Instantiate(model, transform);
            else
            {
                go = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
                Destroy(go.GetComponent<Collider>());
                go.transform.SetParent(transform, false);
                go.transform.localScale = new Vector3(0.5f, 0.05f, 0.5f);
                go.GetComponent<MeshRenderer>().sharedMaterial = FXMaterials.Flash;
            }
            go.name = sealProps[i];
            go.transform.localPosition = offsets[i];
            go.transform.localRotation = model != null ? Quaternion.identity : Quaternion.Euler(90f, 0f, 0f);
            var lg = new GameObject("Glow");
            lg.transform.SetParent(go.transform, false);
            lg.transform.localPosition = new Vector3(0f, 0.25f, 0.6f);
            var l = lg.AddComponent<Light>();
            l.type = LightType.Point; l.range = 3.5f; l.intensity = 1.6f; l.color = new Color(1f, 0.82f, 0.4f); l.shadows = LightShadows.None;
            sockets[i] = go;
            return go;
        }

        public void LightSocket(int i)
        {
            var go = Place(i);
            Game.FX?.SealGlow(go.transform.position + go.transform.up * 0.25f);
            Game.Audio?.Play("seal", go.transform.position, 1f);
        }
    }
}
