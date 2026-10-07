using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Pose del sumo para un momento de un golpe, en el espacio del personaje y en unidades del modelo (u: la altura
    /// de la columna mide 1.435 u; el sumo mide ~5.1 u, así sirve igual para el común y para el Ōzeki x1.35).
    /// Manos y pies son puntos a los que llega cada extremidad con IK: x hacia afuera de ese lado, y desde el piso,
    /// z hacia adelante. Peso 0 = lo que hace el clip.
    /// </summary>
    public struct SumoPose
    {
        public float drop, lean, twist, roll;      // cadera abajo (u); grados: adelante, hombro derecho adelante, hacia la derecha
        public Vector3 handR, handL, footR, footL;
        public float wHandR, wHandL, wFootR, wFootL;

        public static SumoPose Of(float drop, float lean, float twist, float roll,
                                  Vector3 handR, float wHandR, Vector3 handL, float wHandL,
                                  Vector3 footR = default, float wFootR = 0f, Vector3 footL = default, float wFootL = 0f)
            => new SumoPose { drop = drop, lean = lean, twist = twist, roll = roll, handR = handR, wHandR = wHandR, handL = handL, wHandL = wHandL,
                              footR = footR, wFootR = wFootR, footL = footL, wFootL = wFootL };

        /// <summary>La misma pose del otro lado (la bofetada izquierda es la derecha espejada).</summary>
        public SumoPose Mirror() => new SumoPose
        {
            drop = drop, lean = lean, twist = -twist, roll = -roll,
            handR = handL, wHandR = wHandL, handL = handR, wHandL = wHandR,
            footR = footL, wFootR = wFootL, footL = footR, wFootL = wFootR,
        };

        public static SumoPose Lerp(in SumoPose a, in SumoPose b, float t)
        {
            return new SumoPose
            {
                drop = Mathf.LerpUnclamped(a.drop, b.drop, t), lean = Mathf.LerpUnclamped(a.lean, b.lean, t),
                twist = Mathf.LerpUnclamped(a.twist, b.twist, t), roll = Mathf.LerpUnclamped(a.roll, b.roll, t),
                handR = Target(a.handR, a.wHandR, b.handR, b.wHandR, t), wHandR = Mathf.Lerp(a.wHandR, b.wHandR, t),
                handL = Target(a.handL, a.wHandL, b.handL, b.wHandL, t), wHandL = Mathf.Lerp(a.wHandL, b.wHandL, t),
                footR = Target(a.footR, a.wFootR, b.footR, b.wFootR, t), wFootR = Mathf.Lerp(a.wFootR, b.wFootR, t),
                footL = Target(a.footL, a.wFootL, b.footL, b.wFootL, t), wFootL = Mathf.Lerp(a.wFootL, b.wFootL, t),
            };
        }

        // una extremidad que entra o sale (peso 0 de un lado) no viaja desde el origen: queda en el punto del otro
        static Vector3 Target(Vector3 a, float wa, Vector3 b, float wb, float t)
        {
            if (wa <= 0.001f) return b;
            if (wb <= 0.001f) return a;
            return Vector3.LerpUnclamped(a, b, t);
        }

        public float Weight => Mathf.Max(Mathf.Max(wHandR, wHandL), Mathf.Max(wFootR, wFootL)) + Mathf.Abs(drop) + Mathf.Abs(lean) * 0.05f + Mathf.Abs(twist) * 0.05f + Mathf.Abs(roll) * 0.05f;
    }

    /// <summary>
    /// Poses procedurales del sumo encima de sus clips. Los clips del equipo casi no se mueven desde la cámara del
    /// juego (las bofetadas mueven medio brazo, la embestida es un paso): sin esto el aviso del golpe estaba solo en
    /// el anillo. Cada golpe tiene una pose de CARGA y una de GOLPE atadas al reloj del paso (Enemy.Timeline): la
    /// carga se arma en la anticipación, se sostiene en la pausa del apex mientras se cierra el anillo y se suelta en
    /// los ~0.1 s de la suelta, así el cuerpo dice lo mismo que el aviso y el golpe sale en la pose más abierta.
    /// Siluetas que se leen desde arriba a 150 px: la mano atrás a la altura del hombro (bofetada), una pierna arriba
    /// al costado (shiko), agachado con los puños en el piso (tachiai), los brazos abiertos (agarre).
    /// Brazos y piernas se resuelven con IK de dos huesos hacia puntos del espacio del personaje: no dependen del clip
    /// de abajo (si llegan clips nuevos la pose sigue valiendo; 'weight' la baja). Sirve para el esqueleto del equipo
    /// (manos y pies cuelgan de controles IK, no del antebrazo: se mueve el control) y para uno FK.
    /// Las manos que van a pegar se encienden en el último tramo (dorado / rojo), como el filo de la katana.
    /// Corre después del Animator y antes de VariantMotion (110) y SpringChain (120: la tsuna y el delantal cuelgan
    /// de esta pose). En su propio archivo: DefaultExecutionOrder es del script.
    /// </summary>
    [DefaultExecutionOrder(105)]
    public class SumoPoser : MonoBehaviour
    {
        [Tooltip("Cuánto manda la pose procedural sobre el clip (1 = todo; con clips de golpes propios se puede bajar)")]
        [Range(0, 1)] public float weight = 1f;
        /// <summary>Después de posar, este frame (la tsuna encendida del Ōzeki se dibuja sobre la pose final).</summary>
        public event System.Action Posed;

        /// <summary>Un golpe: carga, golpe, cuánto sostiene el golpe y cuánto tarda en volver al clip.</summary>
        public class Move
        {
            public SumoPose wind, strike;
            public float holdAfter = 0.12f, recover = 0.35f;
            public bool run;            // embestida: pisa rápido mientras dura el recorrido (Timeline.sustain)
            public bool tremble;        // tiembla en la pausa del apex (el esfuerzo antes de soltar)
            public bool glowR, glowL, glowFootR, glowFootL;
        }

        // ------------------------------------------------------------------ biblioteca de poses
        static Dictionary<string, Move> moves;
        static Vector3 V(float x, float y, float z) => new Vector3(x, y, z);

        /// <summary>
        /// Poses por nombre de golpe (AttackDef.name). Los del sumo común (Attack1...) usan las del Ōzeki.
        /// Medidas en Blender sobre el esqueleto del sumo (Tools/Blender/characters/sumo_poses.py las renderiza):
        /// hombro en (0.81, 3.34, -0.26), brazo de 1.47 u, cadera a 1.69 u, tobillo a 0.39 u del piso.
        /// </summary>
        public static Dictionary<string, Move> Moves
        {
            get
            {
                if (moves != null) return moves;
                moves = new Dictionary<string, Move>();
                // harite (bofetada derecha): la mano se va atrás a la altura del hombro con el hombro girado, la otra
                // adelante de guardia; suelta: el brazo entero adelante y el cuerpo entra detrás
                var hariteR = new Move
                {
                    wind = SumoPose.Of(0.22f, 4f, -24f, 0f, V(1.35f, 3.3f, -0.75f), 1f, V(0.75f, 2.95f, 0.95f), 0.8f),
                    strike = SumoPose.Of(0.35f, 15f, 30f, 0f, V(0.25f, 3.1f, 2.2f), 1f, V(1.15f, 2.6f, -0.35f), 0.8f),
                    holdAfter = 0.1f, recover = 0.3f, glowR = true,
                };
                var hariteL = Mirrored(hariteR);
                // shiko (pierna derecha arriba): la pierna sube abierta al costado, el cuerpo se carga sobre la otra y
                // las manos en las rodillas; golpe: la planta al piso en cuclillas bien abiertas
                var shikoR = new Move
                {
                    wind = SumoPose.Of(0.2f, 6f, 0f, -18f, V(1.45f, 2.5f, 0.55f), 0.75f, V(0.95f, 1.75f, 0.45f), 0.75f,
                                       V(1.95f, 2.4f, 0.3f), 1f),
                    strike = SumoPose.Of(0.6f, 14f, 0f, 0f, V(1.15f, 1.55f, 0.75f), 0.9f, V(1.15f, 1.55f, 0.75f), 0.9f,
                                         V(1.2f, 0.39f, 0.1f), 1f, V(1.2f, 0.39f, 0.05f), 1f),
                    holdAfter = 0.3f, recover = 0.45f, tremble = true, glowFootR = true,
                };
                var shikoL = Mirrored(shikoR);
                // tachiai: agachado al máximo, los puños apoyados en el piso adelante (el instante antes del choque);
                // golpe: sale con los dos brazos adelante y el cuerpo inclinado
                var tachiai = new Move
                {
                    wind = SumoPose.Of(0.85f, 42f, 0f, 0f, V(0.5f, 0.25f, 1.45f), 1f, V(0.5f, 0.25f, 1.45f), 1f,
                                       V(1.05f, 0.39f, -0.2f), 1f, V(1.05f, 0.39f, -0.2f), 1f),
                    strike = SumoPose.Of(0.35f, 30f, 0f, 0f, V(0.5f, 2.75f, 2.2f), 1f, V(0.5f, 2.75f, 2.2f), 1f),
                    holdAfter = 0.1f, recover = 0.4f, run = true, tremble = true, glowR = true, glowL = true,
                };
                // agarre: los brazos bien abiertos y el pecho afuera (la silueta en T desde arriba); golpe: se cierran adelante
                var grab = new Move
                {
                    wind = SumoPose.Of(0.3f, -6f, 0f, 0f, V(2.05f, 3.3f, 0.55f), 1f, V(2.05f, 3.3f, 0.55f), 1f,
                                       V(1.0f, 0.39f, 0f), 0.8f, V(1.0f, 0.39f, 0f), 0.8f),
                    strike = SumoPose.Of(0.45f, 22f, 0f, 0f, V(0.2f, 2.6f, 1.95f), 1f, V(0.2f, 2.6f, 1.95f), 1f),
                    holdAfter = 0.2f, recover = 0.4f, tremble = true, glowR = true, glowL = true,
                };
                // morote (empujón a dos manos del sumo del lago): carga con las dos manos atrás a la cadera
                var morote = new Move
                {
                    wind = SumoPose.Of(0.35f, 2f, 0f, 0f, V(1.2f, 2.5f, -0.5f), 1f, V(1.2f, 2.5f, -0.5f), 1f),
                    strike = SumoPose.Of(0.4f, 24f, 0f, 0f, V(0.55f, 3.0f, 2.25f), 1f, V(0.55f, 3.0f, 2.25f), 1f),
                    holdAfter = 0.12f, recover = 0.35f, glowR = true, glowL = true,
                };
                // shio: la sal en alto atrás de la cabeza y la tira adelante y arriba (el ritual: no pega)
                var salt = new Move
                {
                    wind = SumoPose.Of(0.05f, -8f, -12f, 0f, V(0.65f, 4.75f, -0.25f), 1f, V(1.0f, 2.05f, 0.15f), 0.6f),
                    strike = SumoPose.Of(0.15f, 8f, 16f, 0f, V(0.35f, 4.2f, 1.7f), 1f, V(1.0f, 2.05f, 0.15f), 0.6f),
                    holdAfter = 0.35f, recover = 0.5f,
                };
                // finta / salto de costado: se agacha para impulsarse y cae abierto
                var hop = new Move
                {
                    wind = SumoPose.Of(0.5f, 18f, 0f, 0f, V(1.1f, 2.2f, 0.6f), 0.7f, V(1.1f, 2.2f, 0.6f), 0.7f),
                    strike = SumoPose.Of(0.15f, 8f, 0f, 0f, V(1.6f, 3.0f, 0.4f), 0.7f, V(1.6f, 3.0f, 0.4f), 0.7f),
                    holdAfter = 0.15f, recover = 0.3f,
                };
                // tropiezo (la embestida contra el bambú): echado atrás con los brazos sueltos
                var stumble = new Move
                {
                    wind = SumoPose.Of(0.25f, -16f, 8f, 6f, V(1.7f, 3.9f, 0.35f), 0.8f, V(1.5f, 3.6f, 0.6f), 0.8f),
                    strike = SumoPose.Of(0.45f, -10f, -6f, -4f, V(1.4f, 2.4f, 0.8f), 0.6f, V(1.4f, 2.4f, 0.8f), 0.6f),
                    holdAfter = 0.2f, recover = 0.5f,
                };
                moves["Harite D"] = hariteR; moves["Harite I"] = hariteL;
                moves["Shiko D"] = shikoR; moves["Shiko I"] = shikoL;
                moves["Tachiai"] = tachiai; moves["Agarre"] = grab; moves["Morote"] = morote;
                moves["Shio"] = salt; moves["Finta"] = hop; moves["Tropiezo"] = stumble;
                // el sumo común: bofetadas, pisotón y embestida con las mismas poses
                moves["Attack1"] = hariteR; moves["Attack2"] = hariteL; moves["Attack3"] = shikoR; moves["Special"] = tachiai;
                return moves;
            }
        }

        static Move Mirrored(Move m) => new Move
        {
            wind = m.wind.Mirror(), strike = m.strike.Mirror(), holdAfter = m.holdAfter, recover = m.recover, run = m.run, tremble = m.tremble,
            glowR = m.glowL, glowL = m.glowR, glowFootR = m.glowFootL, glowFootL = m.glowFootR,
        };

        // ------------------------------------------------------------------ huesos
        class Bone
        {
            public Transform t;
            public Vector3 animPos, writtenPos;
            public Quaternion animRot, writtenRot;
            public bool has;

            public void Restore()
            {
                if (has && t.localRotation == writtenRot && t.localPosition == writtenPos) { t.localRotation = animRot; t.localPosition = animPos; }
                animRot = t.localRotation; animPos = t.localPosition;
            }

            public void Mark() { writtenRot = t.localRotation; writtenPos = t.localPosition; has = true; }
        }

        class Limb
        {
            public Bone upper, lower, control;  // control: el control IK del que cuelga la mano/el pie (null si es FK)
            public Transform end;
            public float lowerLen, side;
        }

        Enemy enemy;
        Bone root, torso, head;
        Limb armR, armL, legR, legL;
        readonly List<Bone> bones = new List<Bone>();
        Renderer watch;
        bool ready, failed;
        float unit = 1f;

        // estado de la pose: la del frame anterior (de ahí arranca el paso siguiente) y el paso en curso
        SumoPose output, snapshot;
        AttackDef curAttack;
        int curTell = -1;
        float lastClock;
        // pose suelta, fuera de un golpe (presentación, cambio de fase, tropiezo): su propio reloj
        Move beat;
        float beatStart, beatWindup;
        bool beatSnap;

        // manos/pies que se encienden en el último tramo del golpe
        Transform glowA, glowB;
        MeshRenderer glowRA, glowRB;
        MaterialPropertyBlock mpb;
        static Mesh glowQuad;

        /// <summary>Unidades del modelo a metros (para el que quiera ubicar cosas sobre el cuerpo: la tsuna).</summary>
        public float Unit => unit;
        public Transform Torso => torso?.t;
        public Transform Head => head?.t;
        public bool Ready => ready;
        /// <summary>Dónde está la mano derecha (la de la sal) en este frame.</summary>
        public Vector3 HandR => ready ? armR.end.position : transform.position;
        /// <summary>Cuánto brillan ahora las manos/el pie del golpe (0..1): lo demás que brilla en el cuerpo (la tsuna
        /// del Ōzeki) se apaga mientras tanto para no competir con el aviso.</summary>
        public float GlowK { get; private set; }

        /// <summary>
        /// Una pose fuera de un golpe (sin daño ni aviso): carga 'windup' segundos, suelta en ~0.1 s y vuelve.
        /// La presentación y el cambio de fase del Ōzeki (el shiko), el tropiezo contra el bambú.
        /// </summary>
        public void PlayBeat(string move, float windup)
        {
            if (!Moves.TryGetValue(move, out var m)) return;
            beat = m;
            beatStart = Time.time;
            beatWindup = Mathf.Max(0.05f, windup);
            beatSnap = true;
        }

        /// <summary>Segundos que faltan para que la pose suelta llegue al golpe (infinito si no hay una).</summary>
        public float BeatEta => beat != null ? beatStart + beatWindup + BeatRelease - Time.time : float.PositiveInfinity;
        const float BeatRelease = 0.1f;

        void Start()
        {
            enemy = GetComponentInParent<Enemy>();
            if (enemy == null) { enabled = false; return; }
            var map = new Dictionary<string, Transform>();
            foreach (var t in GetComponentsInChildren<Transform>(true))
                if (!map.ContainsKey(t.name)) map[t.name] = t;
            Transform F(string n) => map.TryGetValue(n, out var t) ? t : null;
            var tRoot = F("Root"); var tTorso = F("Torso"); var tHead = F("Cabeza");
            if (tRoot == null || tTorso == null || tHead == null) { failed = true; enabled = false; return; }
            root = AddBone(tRoot); torso = AddBone(tTorso); head = AddBone(tHead);
            var a = MakeLimb(F("Brazo.L"), F("Antebrazo.L"), F("Palma.L"));
            var b = MakeLimb(F("Brazo.R"), F("Antebrazo.R"), F("Palma.R"));
            var c = MakeLimb(F("Pierna.L"), F("Tibia.L"), F("pie.L") ?? F("Pie.L"));
            var d = MakeLimb(F("Pierna.R"), F("Tibia.R"), F("pie.R") ?? F("Pie.R"));
            if (a == null || b == null || c == null || d == null) { failed = true; enabled = false; Debug.LogWarning($"[Nindo] SumoPoser: el esqueleto de '{name}' no es el del sumo."); return; }
            // los nombres .L/.R del equipo no coinciden con los lados del personaje: el lado sale de la posición
            armR = a; armL = b; legR = c; legL = d;
            watch = GetComponentInChildren<SkinnedMeshRenderer>();
            mpb = new MaterialPropertyBlock();
        }

        Bone AddBone(Transform t)
        {
            var b = new Bone { t = t };
            bones.Add(b);
            return b;
        }

        Limb MakeLimb(Transform upper, Transform lower, Transform end)
        {
            if (upper == null || lower == null || end == null) return null;
            var l = new Limb { upper = AddBone(upper), lower = AddBone(lower), end = end };
            if (!end.IsChildOf(lower) && end.parent != null) l.control = AddBone(end.parent);
            return l;
        }

        /// <summary>Mide el cuerpo con la primera pose animada (en Start el Animator todavía no corrió).</summary>
        void Measure()
        {
            Transform rt = enemy.transform;
            unit = Vector3.Distance(head.t.position, torso.t.position) / 1.435f;
            if (unit < 1e-3f) unit = 1f;
            foreach (var l in new[] { armR, armL, legR, legL })
            {
                l.lowerLen = Vector3.Distance(l.lower.t.position, l.end.position);
                if (l.lowerLen < 1e-3f) l.lowerLen = 0.6f * unit;
                l.side = Mathf.Sign(Vector3.Dot(l.upper.t.position - rt.position, rt.right));
            }
            if (armR.side < 0f) { var t = armR; armR = armL; armL = t; }
            if (legR.side < 0f) { var t = legR; legR = legL; legL = t; }
            ready = true;
        }

        // ------------------------------------------------------------------ por frame
        void LateUpdate()
        {
            if (failed || enemy == null) return;
            float dt = Time.deltaTime;
            foreach (var b in bones) b.Restore();
            if (!ready) { if (enemy.Anim.Valid) Measure(); else return; }

            output = Desired(dt, out Move glowMove, out float glowEta, out bool danger);
            if (output.Weight * weight > 0.002f && (watch == null || watch.isVisible))
            {
                Apply(output, weight);
                foreach (var b in bones) b.Mark();
            }
            UpdateGlow(glowMove, glowEta, danger);   // después de posar: la luz va donde quedó la mano
            Posed?.Invoke();
        }

        /// <summary>La pose de este frame: la del golpe en curso, la pose suelta o volviendo al clip.</summary>
        SumoPose Desired(float dt, out Move glowMove, out float glowEta, out bool danger)
        {
            glowMove = null; glowEta = float.PositiveInfinity; danger = false;
            var a = enemy.State == EnemyState.Attack ? enemy.CurrentAttack : null;
            if (a != null && Moves.TryGetValue(a.name, out var m))
            {
                beat = null;
                float clock = enemy.StepClock;
                // paso nuevo (otro golpe, o el mismo repetido: el reloj vuelve a cero): arranca desde la pose que había
                if (a != curAttack || enemy.TellId != curTell || clock < lastClock) { snapshot = output; curAttack = a; curTell = enemy.TellId; }
                lastClock = clock;
                var tl = enemy.Timeline;
                // el pie del shiko se enciende para el pisotón (después el golpe es la onda, que viaja sola)
                glowMove = m; danger = a.kind == AttackKind.Unblockable;
                glowEta = a.special == "shiko" ? (clock < tl.T ? tl.T - clock : float.PositiveInfinity) : enemy.StrikeEta;
                if (clipOwned.Contains(a.name)) return SumoPose.Lerp(output, default, 1f - Mathf.Exp(-dt / 0.09f));
                var p = Evaluate(m, clock, tl.ReleaseTime, tl.T, tl.sustain, snapshot);
                // sobre un estado con clip nuevo (los golpes con nombre propio reusan Attack1..Special) el cuerpo ya viene
                // agachado, inclinado y girado: la cadera y el torso del poser son ADITIVOS y lo doblaban (el tachiai
                // llegaba a ~76° de inclinación). Quedan solo las manos y pies (puntos absolutos) y la luz
                if (clipOwned.Contains(a.state)) { p.drop = 0f; p.lean = 0f; p.twist = 0f; p.roll = 0f; }
                return p;
            }
            curAttack = null;
            if (beat != null && enemy.IsAlive)
            {
                if (beatSnap) { snapshot = output; beatSnap = false; }
                float clock = Time.time - beatStart;
                float T = beatWindup + BeatRelease;
                if (clock > T + beat.holdAfter + beat.recover) beat = null;
                else return Evaluate(beat, clock, beatWindup, T, 0f, snapshot);
            }
            // vuelve al clip (cortado por un parry, un golpe, la muerte): rápido pero sin saltos
            return SumoPose.Lerp(output, default, 1f - Mathf.Exp(-dt / 0.09f));
        }

        static readonly float[] noise = { 0.31f, -0.74f, 0.12f, 0.9f, -0.45f, 0.63f, -0.18f, -0.97f };

        /// <summary>
        /// Estados con clip propio (TeamAnims/SumoAnims.fbx) que ya trae la carga y el golpe atados al mismo reloj. Por
        /// nombre de golpe (el sumo común): solo se enciende la mano o el pie que pega. Por estado (los golpes con nombre
        /// propio del Ōzeki y las variantes que los reusan: Harite D, Shiko D, Tachiai, Agarre, Morote): el poser sigue
        /// llevando manos y pies a su pose, pero no le suma cadera ni torso al clip.
        /// </summary>
        static readonly HashSet<string> clipOwned = new HashSet<string> { "Attack1", "Attack2", "Attack3", "Special" };

        SumoPose Evaluate(Move m, float clock, float release, float T, float sustain, in SumoPose from)
        {
            if (clock < release)
            {
                // anticipación: arranca rápido y frena llegando a la carga (como el clip hasta el apex)
                float k = Mathf.Clamp01(clock / Mathf.Max(0.01f, release));
                var p = SumoPose.Lerp(from, m.wind, 1f - (1f - k) * (1f - k));
                if (m.tremble && k > 0.6f) Tremble(ref p, clock, (k - 0.6f) / 0.4f);
                return p;
            }
            if (clock < T)
            {
                // suelta: acelera hasta el golpe
                float k = (clock - release) / Mathf.Max(0.01f, T - release);
                return SumoPose.Lerp(m.wind, m.strike, k * k);
            }
            float after = clock - T;
            if (after < sustain + m.holdAfter)
            {
                var p = m.strike;
                if (m.run && after < sustain) Stamp(ref p, after);
                return p;
            }
            float r = Mathf.Clamp01((after - sustain - m.holdAfter) / Mathf.Max(0.01f, m.recover));
            return SumoPose.Lerp(m.strike, default, r * r * (3f - 2f * r));
        }

        // temblor de esfuerzo sostenido en la carga (a 14 Hz y menos de 1°: se nota sin ensuciar la silueta)
        static void Tremble(ref SumoPose p, float t, float amount)
        {
            int i = (int)(t * 14f) & 7;
            p.drop += noise[i] * 0.025f * amount;
            p.lean += noise[(i + 3) & 7] * 0.9f * amount;
        }

        // embestida: pasos cortos y rápidos (5.5 Hz), si no es una estatua que se desliza
        static void Stamp(ref SumoPose p, float t)
        {
            float ph = t * 5.5f * 2f * Mathf.PI;
            p.footR = V(0.9f, 0.39f + 0.4f * Mathf.Max(0f, Mathf.Sin(ph)), 0.55f * Mathf.Cos(ph)); p.wFootR = 1f;
            p.footL = V(0.9f, 0.39f + 0.4f * Mathf.Max(0f, -Mathf.Sin(ph)), -0.55f * Mathf.Cos(ph)); p.wFootL = 1f;
            p.drop += 0.06f * Mathf.Abs(Mathf.Sin(ph));
        }

        // ------------------------------------------------------------------ aplicar
        void Apply(in SumoPose p, float w)
        {
            Transform rt = enemy.transform;
            Vector3 up = rt.up, fwd = rt.forward, right = rt.right;
            float u = unit;
            // lo que dejó el Animator (manos y pies cuelgan de controles que no siguen a la cadera ni al torso)
            Vector3 handRA = armR.end.position, handLA = armL.end.position, footRA = legR.end.position, footLA = legL.end.position;
            Quaternion handRRot = armR.control != null ? armR.control.t.rotation : Quaternion.identity;
            Quaternion handLRot = armL.control != null ? armL.control.t.rotation : Quaternion.identity;

            // cadera abajo y torso inclinado / girado / de costado (sobre su pivote)
            Vector3 drop = -up * (p.drop * u * w);
            root.t.position += drop;
            Quaternion q = Quaternion.AngleAxis(p.lean * w, Vector3.Cross(up, fwd))
                         * Quaternion.AngleAxis(p.twist * w, -up)
                         * Quaternion.AngleAxis(p.roll * w, Vector3.Cross(up, right));
            Vector3 pivot = torso.t.position;
            torso.t.rotation = q * torso.t.rotation;
            // la cabeza compensa media inclinación: sigue mirando adelante
            head.t.rotation = Quaternion.AngleAxis(-p.lean * 0.45f * w, Vector3.Cross(up, fwd)) * head.t.rotation;

            // piernas: los pies donde los puso el clip (la cadera bajó: se doblan) o donde pide la pose
            Leg(legR, footRA, p.footR, p.wFootR * w, rt, up, fwd, right, u);
            Leg(legL, footLA, p.footL, p.wFootL * w, rt, up, fwd, right, u);
            // brazos: la mano del clip acompaña al torso; la de la pose es un punto del personaje
            Arm(armR, pivot + q * (handRA + drop - pivot), q * handRRot, p.handR, p.wHandR * w, rt, up, fwd, right, u);
            Arm(armL, pivot + q * (handLA + drop - pivot), q * handLRot, p.handL, p.wHandL * w, rt, up, fwd, right, u);
        }

        Vector3 CharPoint(Vector3 c, float side, Transform rt, Vector3 up, Vector3 fwd, Vector3 right, float u)
            => rt.position + (right * (c.x * side) + up * c.y + fwd * c.z) * u;

        void Leg(Limb l, Vector3 animTip, Vector3 pose, float w, Transform rt, Vector3 up, Vector3 fwd, Vector3 right, float u)
        {
            Vector3 target = w > 0.001f ? Vector3.Lerp(animTip, CharPoint(pose, l.side, rt, up, fwd, right, u), w) : animTip;
            // rodilla adelante y bien afuera (cuclillas de sumo)
            Vector3 hint = l.upper.t.position + (fwd * 1.0f + right * (l.side * 0.7f)) * u;
            Vector3 reach = SolveTwoBone(l.upper.t, l.lower.t, l.lowerLen, animTip, target, hint);
            if (l.control != null) l.control.t.position += reach - l.end.position;
        }

        void Arm(Limb l, Vector3 animTip, Quaternion animRot, Vector3 pose, float w, Transform rt, Vector3 up, Vector3 fwd, Vector3 right, float u)
        {
            Vector3 target = w > 0.001f ? Vector3.Lerp(animTip, CharPoint(pose, l.side, rt, up, fwd, right, u), w) : animTip;
            // codo atrás, afuera y abajo
            Vector3 hint = l.upper.t.position + (right * (l.side * 0.7f) - up * 0.9f - fwd * 0.5f) * u;
            Vector3 reach = SolveTwoBone(l.upper.t, l.lower.t, l.lowerLen, l.end.position, target, hint);
            if (l.control != null)
            {
                l.control.t.rotation = animRot;
                l.control.t.position += reach - l.end.position;
            }
        }

        /// <summary>
        /// IK analítico de dos huesos: gira 'upper' para que el codo quede en el plano de 'hint' y 'lower' para que la
        /// punta llegue al objetivo (o lo más cerca, con el brazo estirado). 'tip' es dónde está ahora la punta.
        /// Devuelve el punto alcanzado.
        /// </summary>
        public static Vector3 SolveTwoBone(Transform upper, Transform lower, float lowerLen, Vector3 tip, Vector3 target, Vector3 hint)
        {
            Vector3 a = upper.position, b = lower.position;
            float la = Vector3.Distance(a, b), lb = lowerLen;
            Vector3 at = target - a;
            float d = at.magnitude;
            if (la < 1e-4f || lb < 1e-4f || d < 1e-4f) return tip;
            Vector3 dir = at / d;
            d = Mathf.Clamp(d, Mathf.Abs(la - lb) + 1e-3f, la + lb - 1e-3f);
            float cosA = Mathf.Clamp((la * la + d * d - lb * lb) / (2f * la * d), -1f, 1f);
            Vector3 bend = Vector3.ProjectOnPlane(hint - a, dir);
            if (bend.sqrMagnitude < 1e-8f) bend = Vector3.ProjectOnPlane(b - a, dir);
            if (bend.sqrMagnitude < 1e-8f) bend = Vector3.ProjectOnPlane(Vector3.up, dir);
            bend.Normalize();
            Vector3 elbow = a + dir * (la * cosA) + bend * (la * Mathf.Sqrt(1f - cosA * cosA));
            Quaternion r1 = Quaternion.FromToRotation(b - a, elbow - a);
            upper.rotation = r1 * upper.rotation;
            Vector3 fore = tip - b;
            fore = fore.sqrMagnitude > 1e-8f ? r1 * fore.normalized * lb : (elbow - a).normalized * lb;
            Vector3 reach = a + dir * d;
            lower.rotation = Quaternion.FromToRotation(fore, reach - elbow) * lower.rotation;
            return reach;
        }

        // ------------------------------------------------------------------ manos encendidas
        void UpdateGlow(Move m, float eta, bool danger)
        {
            // las manos (o el pie del shiko) que van a pegar: desde Enemy.GlintLead hasta que sale el golpe
            bool on = m != null && eta <= Enemy.GlintLead && ready && enemy.IsAlive;
            Transform a = null, b = null;
            if (on)
            {
                if (m.glowR) a = armR.end; else if (m.glowFootR) a = legR.end;
                if (m.glowL) b = armL.end; else if (m.glowFootL) b = legL.end;
                // el filo del arma (Enemy.BladeGlint, el destello del cierre del anillo) sale de la mano que pega
                enemy.katanaTip = a != null ? a : b;
            }
            float k = on ? Mathf.InverseLerp(Enemy.GlintLead, TellStyle.Bias(danger ? AttackKind.Unblockable : AttackKind.Heavy), eta) : 0f;
            Color c = (danger ? TellStyle.Crimson : TellStyle.Gold) * Mathf.Lerp(1.2f, 3.5f, k * k);
            Glow(ref glowA, ref glowRA, a, c, k);
            Glow(ref glowB, ref glowRB, b, c, k);
            GlowK = a != null || b != null ? Mathf.Lerp(0.6f, 1f, k) : 0f;
        }

        void Glow(ref Transform g, ref MeshRenderer r, Transform at, Color c, float k)
        {
            if (at == null) { if (r != null && r.enabled) r.enabled = false; return; }
            if (g == null)
            {
                var go = new GameObject("ManoEncendida");
                go.transform.SetParent(transform, false);
                go.AddComponent<MeshFilter>().sharedMesh = GlowQuad;
                r = go.AddComponent<MeshRenderer>();
                r.sharedMaterial = FXMaterials.Additive;
                r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                r.receiveShadows = false;
                g = go.transform;
            }
            r.enabled = true;
            var cam = Game.Camera != null ? Game.Camera.transform : null;
            g.position = at.position + (cam != null ? -cam.forward * 0.4f * unit : Vector3.zero);
            if (cam != null) g.rotation = cam.rotation;
            g.localScale = Vector3.one * (0.9f + 0.5f * k) * unit;
            c.a = Mathf.Lerp(0.55f, 1f, k);
            mpb.Clear();
            mpb.SetColor("_BaseColor", c); mpb.SetColor("_Color", c);
            r.SetPropertyBlock(mpb);
        }

        static Mesh GlowQuad
        {
            get
            {
                if (glowQuad != null) return glowQuad;
                glowQuad = new Mesh { name = "GlowQuad" };
                glowQuad.vertices = new[] { new Vector3(-0.5f, -0.5f, 0), new Vector3(0.5f, -0.5f, 0), new Vector3(-0.5f, 0.5f, 0), new Vector3(0.5f, 0.5f, 0) };
                glowQuad.uv = new[] { new Vector2(0, 0), new Vector2(1, 0), new Vector2(0, 1), new Vector2(1, 1) };
                glowQuad.triangles = new[] { 0, 2, 1, 2, 3, 1 };
                glowQuad.RecalculateBounds();
                return glowQuad;
            }
        }

        void OnDisable()
        {
            if (glowRA != null) glowRA.enabled = false;
            if (glowRB != null) glowRB.enabled = false;
            GlowK = 0f;
        }
    }
}
