using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>Bioma del mapa para vestir a los enemigos: las zonas de Areas agrupadas (el jardín, el bosque, la
    /// muralla y el dojo son el territorio del clan; la montaña Kodoyama, el lago Kohan y el bosque de bambú).</summary>
    public enum Region { Clan, Montana, Lago, Bambu }

    /// <summary>
    /// Variantes de zona de los enemigos comunes: el mismo ninja negro y el mismo sumo, vestidos con lo que pide su
    /// tierra (concepts/variants_sheet.png). Cada variante es:
    ///  * un kit de accesorios (CharacterKits, Tools/Blender/characters/kits/build_kits.py) con lo que se mueve solo;
    ///  * el color de algunos materiales del cuerpo (el traje con el matiz de la zona, el mawashi de cada sumo);
    ///  * un "sabor" de movimiento sin clips nuevos (VariantMotion): la montaña pesada y lenta, el lago fluido, el
    ///    bambú rápido y alerta, el Ōzeki orgulloso;
    ///  * retoques chicos de números que NO tocan los tiempos de los golpes (el aviso de parry sigue igual).
    /// EnemyFactory.Spawn lo aplica apenas arma el modelo, antes de que Enemy/HitFlash miren los renderers.
    /// Sin el kit en NindoContent no hace nada: queda el enemigo de siempre con su tinte.
    /// </summary>
    public static class EnemyVariants
    {
        public class Variant
        {
            public string kit;
            public KeyValuePair<string, Color>[] colors;
            public MotionFlavor motion;
            // multiplicadores (vida, velocidad de desplazamiento, pausa entre combos, tiempo en guardia) y sumas
            public float health = 1f, speed = 1f, cooldown = 1f, guard = 1f, knockResist, distance;
            public int poise;

            public void ApplyStats(EnemyConfig c)
            {
                c.maxHealth = Mathf.Round(c.maxHealth * health);
                c.runSpeed *= speed; c.walkSpeed *= speed;
                c.attackCooldown *= cooldown;
                c.guardTime *= guard;
                c.poiseHits += poise;
                c.knockbackResist = Mathf.Clamp(c.knockbackResist + knockResist, 0f, 0.95f);
                c.preferredDistance += distance;
            }
        }

        static KeyValuePair<string, Color>[] Colors(params (string material, string hex)[] list)
        {
            var r = new KeyValuePair<string, Color>[list.Length];
            for (int i = 0; i < list.Length; i++)
            {
                ColorUtility.TryParseHtmlString(list[i].hex, out var c);
                r[i] = new KeyValuePair<string, Color>(list[i].material, c);
            }
            return r;
        }

        // Colores del cuerpo: los mismos de build_kits.py (BODY_COLORS), así los renders muestran lo que se ve.
        // El traje del ninja sigue siendo negro (el carbón #2e2b2c de export_ninja.py) con apenas el matiz de la
        // zona: más saturado se leía azul marino, como el gi de Kaito. El mawashi del sumo sí cambia de color.
        static readonly KeyValuePair<string, Color>[] NinjaMountain = Colors(("GrisOscuro", "#302f33"));
        static readonly KeyValuePair<string, Color>[] NinjaLake = Colors(("GrisOscuro", "#272c2e"));
        static readonly KeyValuePair<string, Color>[] NinjaBamboo = Colors(("GrisOscuro", "#292c27"));
        static readonly KeyValuePair<string, Color>[] SumoMountain = Colors(("Pollera", "#44474d"), ("PolleraCinto", "#2c2f35"), ("Sagari", "#6b7079"));
        static readonly KeyValuePair<string, Color>[] SumoLake = Colors(("Pollera", "#1f4a5e"), ("PolleraCinto", "#173544"), ("Sagari", "#9fd0d6"));
        static readonly KeyValuePair<string, Color>[] SumoBamboo = Colors(("Pollera", "#2f4a2a"), ("PolleraCinto", "#1f3320"), ("Sagari", "#b8a35a"));
        static readonly KeyValuePair<string, Color>[] OzekiColors = Colors(("Pollera", "#5b3a6b"), ("PolleraCinto", "#3a2446"), ("Sagari", "#d9a93a"));

        /// <summary>
        /// La variante de un arquetipo en una región (null = no se viste: jefes con modelo propio, clones de Kage).
        /// sumo_mountain ya ES el sumo de la montaña (con su vida y daño en EnemyArchetypes): lleva el kit sin los
        /// retoques de números; el Ōzeki lleva el suyo en cualquier lado.
        /// </summary>
        public static Variant For(string archetype, Region region)
        {
            switch (archetype)
            {
                case "ninja":
                case "ninja_elite":
                {
                    string elite = archetype == "ninja_elite" ? "_elite" : "";
                    switch (region)
                    {
                        case Region.Montana: return Mountain(new Variant { kit = "ninja_mountain" + elite, colors = NinjaMountain });
                        case Region.Lago: return Lake(new Variant { kit = "ninja_lake" + elite, colors = NinjaLake });
                        case Region.Bambu: return Bamboo(new Variant { kit = "ninja_bamboo" + elite, colors = NinjaBamboo });
                        default: return new Variant { kit = archetype == "ninja_elite" ? "ninja_elite" : "ninja_default" };
                    }
                }
                case "sumo":
                    switch (region)
                    {
                        case Region.Montana: return Mountain(new Variant { kit = "sumo_mountain", colors = SumoMountain });
                        case Region.Lago: return Lake(new Variant { kit = "sumo_lake", colors = SumoLake });
                        case Region.Bambu: return Bamboo(new Variant { kit = "sumo_bamboo", colors = SumoBamboo });
                        default: return new Variant { kit = "sumo_default" };
                    }
                case "sumo_mountain":
                    return new Variant { kit = "sumo_mountain", colors = SumoMountain, motion = MotionFlavor.Mountain };
                case "ozeki":
                    return new Variant { kit = "ozeki", colors = OzekiColors, motion = MotionFlavor.Champion };
                default:
                    return null;
            }
        }

        // montaña: abrigados contra el frío, más pesados: aguantan más y se mueven más lento
        static Variant Mountain(Variant v)
        {
            v.motion = MotionFlavor.Mountain;
            v.health = 1.15f; v.speed = 0.92f; v.poise = 1; v.knockResist = 0.1f;
            return v;
        }

        // lago: fluidos como el agua: vuelven antes al ataque y salen antes de la guardia
        static Variant Lake(Variant v)
        {
            v.motion = MotionFlavor.Lake;
            v.speed = 1.04f; v.cooldown = 0.9f; v.guard = 0.85f;
            return v;
        }

        // bambú: livianos y rápidos: menos vida, más velocidad y rodean a Kaito un poco más lejos
        static Variant Bamboo(Variant v)
        {
            v.motion = MotionFlavor.Bamboo;
            v.health = 0.9f; v.speed = 1.1f; v.cooldown = 0.88f; v.distance = 0.4f;
            return v;
        }

        // ------------------------------------------------------------------ región por posición
        static Zone[] zoneCache;
        static int zoneFrame = -1;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void Reset() { zoneCache = null; zoneFrame = -1; }

        /// <summary>Región de un punto con el mismo criterio que Zone.Tick (mayor prioridad, después la más chica).</summary>
        public static Region RegionAt(Vector3 pos)
        {
            // las zonas se buscan una vez por frame: un encuentro crea todos sus enemigos en el mismo frame
            if (zoneCache == null || zoneFrame != Time.frameCount)
            {
                zoneCache = Object.FindObjectsByType<Zone>(FindObjectsSortMode.None);
                zoneFrame = Time.frameCount;
            }
            Zone best = null;
            foreach (var z in zoneCache)
            {
                if (z == null || !z.Contains(pos)) continue;
                if (best == null || z.priority > best.priority || (z.priority == best.priority && z.radius < best.radius)) best = z;
            }
            switch (best != null ? best.id : "")
            {
                case "montana": return Region.Montana;
                case "lago": return Region.Lago;
                case "bambu": return Region.Bambu;
                default: return Region.Clan;
            }
        }

        /// <summary>
        /// Viste al enemigo recién armado (EnemyFactory.Spawn, antes del tinte y de agregar Enemy). Con el kit puesto
        /// el tinte de EnemyArchetypes se apaga: el rojo del élite, el azul del sumo de la montaña y el del Ōzeki
        /// ahora son piezas del kit (la máscara oni, las hombreras laqueadas, el delantal violeta).
        /// </summary>
        public static void Apply(string archetype, EnemyConfig cfg, Animator anim, Vector3 pos)
        {
            if (anim == null || cfg == null) return;
            var v = For(archetype, RegionAt(pos));
            if (v == null || CharacterKits.Attach(anim.transform, v.kit) == null) return;
            cfg.tintStrength = 0f;
            CharacterKits.Recolor(anim.transform, v.colors);
            v.ApplyStats(cfg);
            if (v.motion != null) anim.gameObject.AddComponent<VariantMotion>().flavor = v.motion;
        }
    }

    /// <summary>Cómo se mueve una variante sin clips nuevos (VariantMotion).</summary>
    [System.Serializable]
    public class MotionFlavor
    {
        [Tooltip("Velocidad de la animación de locomoción quieto y corriendo (nunca en ataques: el golpe sigue en su tiempo)")]
        public float idleSpeed = 1f, moveSpeed = 1f;
        [Tooltip("Grados de la columna hacia adelante (+) o atrás (-)")] public float lean;
        [Tooltip("Grados de los hombros hacia adelante (encogidos +, sacando pecho -)")] public float hunch;
        [Tooltip("Grados de la cabeza hacia abajo (+): compensa la inclinación para seguir mirando al frente")] public float headPitch;
        [Tooltip("Respiración: grados de la columna y ciclos por segundo")] public float breathe, breatheHz = 0.3f;
        [Tooltip("Vaivén lateral que sube por la columna hasta la cabeza, atrasado: grados y ciclos por segundo")] public float sway, swayHz = 0.4f;
        [Tooltip("Miradas rápidas a los costados quieto: grados (0 = no) y segundos entre una y otra")] public float scan, scanEvery = 1.6f;

        /// <summary>Montaña: encorvado contra el viento, respiración honda y lenta, todo un poco más pesado.</summary>
        public static readonly MotionFlavor Mountain = new MotionFlavor
        { idleSpeed = 0.8f, moveSpeed = 0.92f, lean = 7f, hunch = 6f, headPitch = -5f, breathe = 2.6f, breatheHz = 0.26f };

        /// <summary>Lago: el cuerpo se mece como el agua, una ola que sube de la cintura a la cabeza.</summary>
        public static readonly MotionFlavor Lake = new MotionFlavor
        { idleSpeed = 0.95f, moveSpeed = 1.04f, lean = 2f, breathe = 1.2f, breatheHz = 0.34f, sway = 3.5f, swayHz = 0.42f };

        /// <summary>Bambú: agazapado y nervioso, la cabeza salta de un lado a otro buscando a Kaito.</summary>
        public static readonly MotionFlavor Bamboo = new MotionFlavor
        { idleSpeed = 1.18f, moveSpeed = 1.1f, lean = 9f, headPitch = -6f, breathe = 1f, breatheHz = 0.6f, scan = 24f, scanEvery = 1.5f };

        /// <summary>Ōzeki: el campeón saca pecho y respira lento; nada de apuro.</summary>
        public static readonly MotionFlavor Champion = new MotionFlavor
        { idleSpeed = 0.85f, moveSpeed = 0.95f, lean = -5f, hunch = -4f, headPitch = 3f, breathe = 2f, breatheHz = 0.24f };
    }

    /// <summary>
    /// Aplica un MotionFlavor sobre la animación del equipo: retoca la velocidad del Animator y suma rotaciones a
    /// columna, hombros y cabeza DESPUÉS del Animator. Solo en el estado de locomoción (quieto, caminando, rodeando):
    /// al entrar a un ataque, golpe o guardia se desvanece en ~0.1 s, así las poses de los golpes (y el aviso de
    /// parry que se lee en ellas) quedan exactas. Los giros van en ejes del personaje (adelante, derecha, arriba),
    /// no en los locales de cada hueso: sirve igual para el ninja y para el sumo.
    /// Corre después de Enemy (que fija Animator.speed en su Update) y antes de SpringChain (que cuelga del pose).
    /// </summary>
    [DefaultExecutionOrder(110)]
    public class VariantMotion : MonoBehaviour
    {
        public MotionFlavor flavor;

        class Bone
        {
            public Transform t;
            public Quaternion written, animated;
            public bool has;
        }

        static readonly int SpeedParam = Animator.StringToHash("Speed");
        Enemy enemy;
        Animator animator;
        Renderer watch;
        Bone lower, upper, head, shoulderL, shoulderR;
        bool hasSpeed;
        float weight, phase, scanYaw, scanTarget, nextScan;

        void Start()
        {
            enemy = GetComponentInParent<Enemy>();
            animator = GetComponent<Animator>();
            if (enemy == null || animator == null || flavor == null) { enabled = false; return; }
            foreach (var p in animator.parameters)
                if (p.nameHash == SpeedParam && p.type == AnimatorControllerParameterType.Float) hasSpeed = true;
            var map = new Dictionary<string, Transform>();
            foreach (var t in GetComponentsInChildren<Transform>(true))
                if (!map.ContainsKey(t.name)) map[t.name] = t;
            Bone Find(params string[] names)
            {
                foreach (var n in names) if (map.TryGetValue(n, out var t)) return new Bone { t = t };
                return null;
            }
            // ninja: EspaldaBaja/EspaldaAlta; sumo: un solo Torso (lleva toda la inclinación)
            lower = Find("EspaldaBaja");
            upper = Find("EspaldaAlta", "Torso");
            head = Find("Cabeza", "cabeza");
            shoulderL = Find("Hombro.L");
            shoulderR = Find("Hombro.R");
            watch = GetComponentInChildren<SkinnedMeshRenderer>();
            phase = Random.value * 10f;                   // que dos del mismo grupo no respiren a la par
            nextScan = Time.time + Random.Range(0.3f, flavor.scanEvery);
        }

        bool InLocomotion => enemy.IsAlive && enemy.State != EnemyState.Scripted && enemy.Anim.Current == enemy.config.animLocomotion;

        float Speed01 => hasSpeed ? Mathf.Clamp01(animator.GetFloat(SpeedParam)) : 0f;

        void Update()
        {
            // Enemy fija Animator.speed en cada Update (CharacterAnimator.Tick): se escala recién si sigue siendo ese
            // valor (congelado por hit-stop o un frame sin Tick no se toca, y nunca se acumula)
            if (!InLocomotion || enemy.Anim.Frozen) return;
            float s = enemy.Anim.StateSpeed;
            if (Mathf.Abs(animator.speed - s) < 1e-4f) animator.speed = s * Mathf.Lerp(flavor.idleSpeed, flavor.moveSpeed, Speed01);
        }

        void LateUpdate()
        {
            float dt = Time.deltaTime;
            if (dt <= 0f) return;
            weight = Mathf.MoveTowards(weight, InLocomotion ? 1f : 0f, dt * 10f);
            if (watch != null && !watch.isVisible) return;
            // un hueso que el Animator no escribió este frame (cullado, sin curva) vuelve a su pose antes de sumar
            Restore(lower); Restore(upper); Restore(head); Restore(shoulderL); Restore(shoulderR);
            if (weight <= 0.001f) return;

            var root = enemy.transform;
            Vector3 right = root.right, fwd = root.forward;
            float t = Time.time + phase;
            float still = 1f - Speed01;
            float breathe = Mathf.Sin(t * flavor.breatheHz * 2f * Mathf.PI) * flavor.breathe * 0.5f * (0.4f + 0.6f * still);
            float sway = flavor.sway * (0.5f + 0.5f * still);
            float w = flavor.swayHz * 2f * Mathf.PI;
            float lean = flavor.lean * weight;

            // inclinación repartida en la columna (40 % abajo, 60 % arriba; el sumo tiene un solo hueso)
            float lowerShare = lower != null ? 0.4f : 0f;
            Rotate(lower, right, lean * lowerShare, fwd, Mathf.Sin(t * w) * sway * weight);
            Rotate(upper, right, lean * (1f - lowerShare) + breathe * weight, fwd, Mathf.Sin(t * w - 0.8f) * sway * 0.6f * weight);
            Rotate(shoulderL, right, flavor.hunch * weight, fwd, 0f);
            Rotate(shoulderR, right, flavor.hunch * weight, fwd, 0f);

            // la cabeza compensa la inclinación (sigue mirando a Kaito), cierra la ola del lago y busca en el bambú
            if (flavor.scan > 0f && Time.time >= nextScan)
            {
                scanTarget = still > 0.6f && Random.value < 0.7f ? Random.Range(-flavor.scan, flavor.scan) : 0f;
                nextScan = Time.time + flavor.scanEvery * Random.Range(0.6f, 1.4f);
            }
            scanYaw = Mathf.MoveTowards(scanYaw, scanTarget * still, dt * 260f);     // un giro seco, no un paneo
            if (head != null && head.t != null)
            {
                head.t.rotation = Quaternion.AngleAxis(scanYaw * weight, Vector3.up)
                                * Quaternion.AngleAxis(flavor.headPitch * weight - breathe * 0.5f * weight, right)
                                * Quaternion.AngleAxis(-Mathf.Sin(t * w - 1.6f) * sway * 0.5f * weight, fwd)
                                * head.t.rotation;
                Mark(head);
            }
        }

        static void Restore(Bone b)
        {
            if (b == null || b.t == null) return;
            if (b.has && b.t.localRotation == b.written) b.t.localRotation = b.animated;
            b.animated = b.t.localRotation;
        }

        static void Mark(Bone b)
        {
            b.written = b.t.localRotation;
            b.has = true;
        }

        static void Rotate(Bone b, Vector3 pitchAxis, float pitch, Vector3 rollAxis, float roll)
        {
            if (b == null || b.t == null) return;
            b.t.rotation = Quaternion.AngleAxis(pitch, pitchAxis) * Quaternion.AngleAxis(roll, rollAxis) * b.t.rotation;
            Mark(b);
        }
    }
}
