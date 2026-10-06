using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Movimiento secundario de los accesorios de los kits (CharacterKits): colas del hachimaki y de la bandana de
    /// Kaito, la capa de paja de la montaña, los faldones, shide, borlas, el flotador del lago...
    ///
    /// Verlet por cadena ('Acc_&lt;Nombre&gt;_0..n' + 'Acc_&lt;Nombre&gt;_end', las arma build_kits.py), en espacio mundo:
    ///  * la inercia sale sola: las partículas conservan su posición en el mundo y el hueso del que cuelgan se
    ///    las lleva; el arrastre del aire (airDrag, sobre la velocidad en el mundo) hace la estela al correr y la
    ///    amortiguación (damping, sobre la velocidad relativa al ancla) que no queden oscilando;
    ///  * stiffness tira hacia la pose que traen los huesos (la capa conserva su forma, una cinta casi nada);
    ///  * largo fijo por tramo, ángulo máximo respecto de esa pose, esferas del cuerpo y el piso. Cada esfera es un
    ///    hueso 'AccCol_&lt;Nombre&gt;_&lt;radio en centésimas del archivo&gt;' con un hijo '_r' a un radio de distancia: el
    ///    radio se mide en el mundo y de la relación sale la escala de los grosores (vale con cualquier escala);
    ///  * un viento suave en reposo (flutter) para que el papel y las cintas nunca queden muertos.
    /// Los parámetros por tipo están en ProfileFor (por el nombre de la cadena) y se ajustaron con la simulación
    /// de Tools/Blender/characters/kits/spring_sim.py (mismo algoritmo). Pasos de 1/60 s o menos, como mucho 4
    /// por frame; con el renderer fuera de cámara no simula y al volver arranca de la pose animada.
    /// Corre después del Animator, de ProceduralMotion y de EnemyVariants (que retocan la pose).
    /// </summary>
    [DefaultExecutionOrder(120)]
    public class SpringChain : MonoBehaviour
    {
        [System.Serializable]
        public struct Profile
        {
            [Tooltip("Tirón por paso (a 60 Hz) hacia la pose animada: 0 = cuelga solo por gravedad")] public float stiffness;
            [Tooltip("Pérdida por paso de la velocidad relativa al hueso del que cuelga")] public float damping;
            [Tooltip("Pérdida por paso de la velocidad en el mundo (aire): la estela al correr")] public float airDrag;
            public float gravity;
            [Tooltip("Grados que se puede apartar de la pose animada")] public float maxAngle;
            [Tooltip("Viento en reposo (m/s²)")] public float flutter;
            [Tooltip("Grosor para chocar con el cuerpo (unidades del FBX del kit)")] public float radius;

            public Profile(float stiffness, float damping, float airDrag, float gravity, float maxAngle, float flutter, float radius)
            {
                this.stiffness = stiffness; this.damping = damping; this.airDrag = airDrag; this.gravity = gravity;
                this.maxAngle = maxAngle; this.flutter = flutter; this.radius = radius;
            }
        }

        /// <summary>
        /// Parámetros por tipo de accesorio (el nombre de la cadena sin el sufijo: TailA -> Tail). Medidos con
        /// Tools/Blender/characters/kits/spring_sim.py (carrera a 5 m/s, frenada, media vuelta, empujón): las cintas
        /// se van 35-50° atrás corriendo, la capa y los faldones ~10°, las placas de caña ~4°; todo se asienta en
        /// 0.3-0.9 s salvo el flotador, que es un péndulo.
        /// </summary>
        public static Profile ProfileFor(string kind)
        {
            switch (kind)
            {
                // cintas de tela: livianas, flamean al correr y casi no guardan forma
                case "Tail": return new Profile(0.03f, 0.06f, 0.070f, 1f, 115f, 1.6f, 0.04f);
                case "Tie": return new Profile(0.05f, 0.08f, 0.060f, 1f, 110f, 1.2f, 0.04f);
                case "Leaf": return new Profile(0.04f, 0.06f, 0.080f, 0.7f, 115f, 2.0f, 0.03f);
                // papel: el más nervioso con el viento
                case "Shide": return new Profile(0.06f, 0.05f, 0.090f, 0.8f, 85f, 2.6f, 0.02f);
                // capa de paja: pesada, se va atrás unos 10° corriendo, se mece una vez al frenar y se queda
                case "Cape": return new Profile(0.035f, 0.11f, 0.038f, 1f, 40f, 0.5f, 0.05f);
                case "Flap": return new Profile(0.06f, 0.10f, 0.035f, 1f, 55f, 0.8f, 0.03f);
                case "Apron": return new Profile(0.04f, 0.10f, 0.035f, 1f, 50f, 0.6f, 0.05f);
                // péndulos: el flotador de vidrio y las borlas de soga con su mechón de piel en la punta
                case "Float": return new Profile(0.00f, 0.03f, 0.010f, 1f, 70f, 0.3f, 0.10f);
                case "Tassel": return new Profile(0.04f, 0.06f, 0.025f, 1f, 75f, 0.5f, 0.05f);
                case "Chimes": return new Profile(0.07f, 0.09f, 0.022f, 1f, 50f, 0.4f, 0.05f);
                // placas de caña: rígidas, apenas acompañan las piernas
                case "Tasset": return new Profile(0.10f, 0.15f, 0.020f, 1f, 30f, 0.3f, 0.04f);
                default: return new Profile(0.05f, 0.08f, 0.050f, 1f, 90f, 1.0f, 0.04f);
            }
        }

        /// <summary>Paso máximo de la simulación (s).</summary>
        public const float Step = 1f / 60f;
        const int MaxSteps = 4;
        /// <summary>Si el ancla salta más que esto en un frame (teletransporte, respawn) se reinicia en la pose animada (m).</summary>
        const float TeleportDistance = 1.5f;

        class Chain
        {
            public string kind;
            public Transform[] bones;       // n huesos
            public Transform end;           // punta (hueso _end)
            public Profile p;
            public Vector3[] pos, prev;     // n + 1 partículas (0 = cabeza del primer hueso, va con el ancla)
            public Vector3[] target, lastTarget;
            public Quaternion[] restLocal;
            public float phase;
        }

        readonly List<Chain> chains = new List<Chain>();
        readonly List<(Transform t, Transform rim, float fileRadius)> colliders = new List<(Transform, Transform, float)>();
        // esferas de este frame: centro del frame anterior, centro actual y radio (los pasos intermedios interpolan
        // igual que las anclas; con el centro final la cadera "llegaba antes" y a 30 fps las cintas flameaban menos)
        readonly List<(Vector3 from, Vector3 to, float r)> spheres = new List<(Vector3, Vector3, float)>();
        Vector3[] lastCenters = new Vector3[0];
        Renderer watch;
        Transform owner;
        bool reset = true;
        float lastStep = Step;
        Vector3 pendingKick;

        /// <summary>El personaje (raíz que se mueve por el mundo): para el piso y las direcciones de Kick.</summary>
        public Transform Owner
        {
            get
            {
                if (owner == null)
                {
                    owner = transform;
                    for (var t = transform.parent; t != null; t = t.parent)
                        if (t.GetComponent<CharacterController>() != null || t.GetComponent<Enemy>() != null) { owner = t; break; }
                }
                return owner;
            }
        }

        /// <summary>Busca todas las cadenas y colisiones colgadas del modelo (se llama después de cada kit).</summary>
        public void Rebuild(Renderer visibility)
        {
            if (visibility != null) watch = visibility;
            chains.Clear();
            colliders.Clear();
            foreach (var t in GetComponentsInChildren<Transform>(true))
            {
                string n = t.name;
                if (n.StartsWith(CharacterKits.ColliderPrefix))
                {
                    int u = n.LastIndexOf('_');
                    var rim = t.Find(n + "_r");
                    if (rim != null && u > 0 && int.TryParse(n.Substring(u + 1), out int cm) && cm > 0) colliders.Add((t, rim, cm / 100f));
                    continue;
                }
                if (!n.StartsWith(CharacterKits.ChainPrefix) || !n.EndsWith("_0")) continue;
                if (t.parent == null || t.parent.name.StartsWith(CharacterKits.ChainPrefix)) continue;
                var c = Walk(t, n.Substring(CharacterKits.ChainPrefix.Length, n.Length - CharacterKits.ChainPrefix.Length - 2));
                if (c != null) chains.Add(c);
            }
            lastCenters = new Vector3[colliders.Count];
            reset = true;
        }

        Chain Walk(Transform first, string name)
        {
            var bones = new List<Transform> { first };
            Transform end = null;
            for (var cur = first; cur != null && end == null;)
            {
                Transform next = null;
                string nextName = $"{CharacterKits.ChainPrefix}{name}_{bones.Count}", endName = $"{CharacterKits.ChainPrefix}{name}_end";
                foreach (Transform ch in cur)
                {
                    if (ch.name == nextName) next = ch;
                    else if (ch.name == endName) end = ch;
                }
                if (next != null) bones.Add(next);
                cur = next;
            }
            if (end == null) return null;
            int n = bones.Count;
            var c = new Chain
            {
                kind = Kind(name), bones = bones.ToArray(), end = end,
                pos = new Vector3[n + 1], prev = new Vector3[n + 1], target = new Vector3[n + 1], lastTarget = new Vector3[n + 1],
                restLocal = new Quaternion[n], phase = (name.GetHashCode() & 1023) * 0.0061f,
            };
            c.p = ProfileFor(c.kind);
            for (int i = 0; i < n; i++) c.restLocal[i] = c.bones[i].localRotation;
            return c;
        }

        /// <summary>'TailA' -> 'Tail', 'Shide01' -> 'Shide', 'TassetFL' -> 'Tasset': la mayúscula y sus minúsculas.</summary>
        static string Kind(string name)
        {
            int i = 1;
            while (i < name.Length && char.IsLower(name[i])) i++;
            return name.Substring(0, i);
        }

        /// <summary>
        /// Suma una velocidad (m/s, mundo) a todas las puntas: un latigazo (la bandana que se ata sola). Se aplica
        /// en el próximo paso simulado, después del reinicio que hace la cadena al volver a verse.
        /// </summary>
        public void Kick(Vector3 velocity) => pendingKick += velocity;

        void LateUpdate()
        {
            float dt = Time.deltaTime;
            if (dt <= 0f || chains.Count == 0) return;
            if (watch != null && !watch.isVisible) { reset = true; return; }

            float ground = Owner.position.y;
            // pose animada: las cadenas vuelven a su rotación de reposo relativa al hueso del que cuelgan
            bool teleported = false;
            foreach (var c in chains)
            {
                int n = c.bones.Length;
                for (int i = 0; i < n; i++) c.bones[i].localRotation = c.restLocal[i];
                for (int i = 0; i < n; i++) c.target[i] = c.bones[i].position;
                c.target[n] = c.end.position;
                if (!reset && (c.target[0] - c.lastTarget[0]).sqrMagnitude > TeleportDistance * TeleportDistance) teleported = true;
            }
            bool fresh = reset || teleported;
            if (fresh)
            {
                foreach (var c in chains)
                    for (int i = 0; i < c.pos.Length; i++) c.pos[i] = c.prev[i] = c.lastTarget[i] = c.target[i];
                reset = false;
            }
            // esferas en el mundo y metros por unidad del archivo (de la primera esfera; sin esferas, la escala)
            float scale = transform.lossyScale.x;
            spheres.Clear();
            for (int i = 0; i < colliders.Count; i++)
            {
                var (t, rim, fr) = colliders[i];
                float r = Vector3.Distance(rim.position, t.position);
                if (i == 0) scale = r / fr;
                Vector3 to = t.position;
                spheres.Add((fresh ? to : lastCenters[i], to, r));
                lastCenters[i] = to;
            }

            int steps = Mathf.Clamp(Mathf.CeilToInt(dt / Step - 0.001f), 1, MaxSteps);
            float h = Mathf.Min(dt / steps, Step);
            Vector3 wind = Wind(Time.time);
            if (pendingKick != Vector3.zero)
            {
                foreach (var c in chains)
                    for (int i = 1; i < c.pos.Length; i++) c.prev[i] -= pendingKick * h;
                pendingKick = Vector3.zero;
            }
            for (int s = 1; s <= steps; s++)
            {
                float u = (float)s / steps;
                foreach (var c in chains) Simulate(c, u, h, scale, ground, wind);
                lastStep = h;
            }

            foreach (var c in chains)
            {
                WriteBack(c);
                for (int i = 0; i < c.target.Length; i++) c.lastTarget[i] = c.target[i];
            }
        }

        /// <summary>Viento suave que cambia de dirección despacio (el mismo para todos: la escena "respira" junta).</summary>
        static Vector3 Wind(float t)
        {
            float a = 0.6f + Mathf.Sin(t * 0.11f) * 0.5f;
            return new Vector3(Mathf.Cos(a), 0f, Mathf.Sin(a));
        }

        void Simulate(Chain c, float u, float h, float scale, float ground, Vector3 wind)
        {
            var p = c.p;
            int n = c.pos.Length - 1;
            // parámetros dados por paso de 1/60 s: se corrigen para el paso real. La rigidez es un tirón de posición
            // que el verlet convierte en velocidad: es un resorte (aceleración * h²) y escala con k², no con k
            // (con k a 144 fps quedaba 2.4 veces más rígido y las colas casi no flameaban)
            float k = h / Step;
            float stiff = p.stiffness * k * k;
            float damp = Mathf.Pow(1f - p.damping, k);
            float drag = Mathf.Pow(1f - p.airDrag, k);
            float corr = h / lastStep;               // verlet con paso variable
            Vector3 a0 = Vector3.Lerp(c.lastTarget[0], c.target[0], u);
            Vector3 anchorVel = a0 - c.pos[0];        // lo que se movió el ancla en este paso
            c.pos[0] = c.prev[0] = a0;
            float t = Time.time;
            Vector3 gust = wind * (p.flutter * (0.55f + 0.45f * Mathf.Sin(t * 1.7f + c.phase * 6.3f)))
                         + Vector3.Cross(wind, Vector3.up) * (p.flutter * 0.5f * Mathf.Sin(t * 3.1f + c.phase * 11f));
            Vector3 accel = (Physics.gravity * p.gravity + gust) * (h * h);
            float maxRad = p.maxAngle * Mathf.Deg2Rad;
            for (int i = 1; i <= n; i++)
            {
                Vector3 ti = Vector3.Lerp(c.lastTarget[i], c.target[i], u);
                Vector3 tp = Vector3.Lerp(c.lastTarget[i - 1], c.target[i - 1], u);
                Vector3 restSeg = ti - tp;
                float len = restSeg.magnitude;
                if (len < 1e-5f) { c.pos[i] = c.prev[i] = c.pos[i - 1]; continue; }

                Vector3 vel = (c.pos[i] - c.prev[i]) * corr * drag;
                vel = anchorVel + (vel - anchorVel) * damp;
                c.prev[i] = c.pos[i];
                Vector3 x = c.pos[i] + vel + accel;
                // forma: hacia donde la pondría la animación, medido desde la partícula de arriba ya simulada
                x = Vector3.Lerp(x, c.pos[i - 1] + restSeg, stiff);
                foreach (var (from, to, sr) in spheres)
                {
                    float r = sr + p.radius * scale;
                    Vector3 sc = Vector3.Lerp(from, to, u);
                    Vector3 d = x - sc;
                    float m = d.sqrMagnitude;
                    if (m < r * r && m > 1e-10f) x = sc + d * (r / Mathf.Sqrt(m));
                }
                float floor = ground + p.radius * scale;
                if (x.y < floor) x.y = floor;
                // largo del tramo y ángulo máximo respecto de la pose animada
                Vector3 dir = x - c.pos[i - 1];
                if (dir.sqrMagnitude < 1e-10f) dir = restSeg;
                dir = Vector3.RotateTowards(restSeg / len, dir.normalized, maxRad, 0f);
                c.pos[i] = c.pos[i - 1] + dir * len;
            }
        }

        static void WriteBack(Chain c)
        {
            int n = c.bones.Length;
            for (int i = 0; i < n; i++)
            {
                var b = c.bones[i];
                Vector3 child = i + 1 < n ? c.bones[i + 1].position : c.end.position;
                Vector3 cur = child - b.position, want = c.pos[i + 1] - b.position;
                if (cur.sqrMagnitude > 1e-10f && want.sqrMagnitude > 1e-10f)
                    b.rotation = Quaternion.FromToRotation(cur, want) * b.rotation;
            }
        }
    }
}
