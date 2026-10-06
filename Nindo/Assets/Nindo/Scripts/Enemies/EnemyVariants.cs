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
    ///  * retoques chicos de números que NO tocan los tiempos de los golpes (el aviso de parry sigue igual);
    ///  * golpes propios de la zona (EnemyArchetypes.*Moves): la montaña cierra con un tajo imparable, el lago gira
    ///    y tira el arpón, el bambú entra de un salto y se repliega; sus sumos pisan, empujan o fintean.
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
            /// <summary>Golpes propios de la zona (EnemyArchetypes): se suman a los del arquetipo.</summary>
            public System.Action<EnemyConfig> moves;

            public void ApplyStats(EnemyConfig c)
            {
                c.maxHealth = Mathf.Round(c.maxHealth * health);
                c.runSpeed *= speed; c.walkSpeed *= speed;
                c.attackCooldown *= cooldown;
                c.guardTime *= guard;
                c.poiseHits += poise;
                c.knockbackResist = Mathf.Clamp(c.knockbackResist + knockResist, 0f, 0.95f);
                c.preferredDistance += distance;
                moves?.Invoke(c);
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
                        case Region.Montana: return Mountain(new Variant { kit = "ninja_mountain" + elite, colors = NinjaMountain, moves = EnemyArchetypes.NinjaMountainMoves });
                        case Region.Lago: return Lake(new Variant { kit = "ninja_lake" + elite, colors = NinjaLake, moves = EnemyArchetypes.NinjaLakeMoves });
                        case Region.Bambu: return Bamboo(new Variant { kit = "ninja_bamboo" + elite, colors = NinjaBamboo, moves = EnemyArchetypes.NinjaBambooMoves });
                        default: return new Variant { kit = archetype == "ninja_elite" ? "ninja_elite" : "ninja_default" };
                    }
                }
                case "sumo":
                    switch (region)
                    {
                        case Region.Montana: return Mountain(new Variant { kit = "sumo_mountain", colors = SumoMountain, moves = EnemyArchetypes.SumoMountainMoves });
                        case Region.Lago: return Lake(new Variant { kit = "sumo_lake", colors = SumoLake, moves = EnemyArchetypes.SumoLakeMoves });
                        case Region.Bambu: return Bamboo(new Variant { kit = "sumo_bamboo", colors = SumoBamboo, moves = EnemyArchetypes.SumoBambooMoves });
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

        // montaña: abrigados contra el frío, más pesados: aguantan más, se mueven más lento y se cubren más tiempo
        static Variant Mountain(Variant v)
        {
            v.motion = MotionFlavor.Mountain;
            v.health = 1.15f; v.speed = 0.92f; v.poise = 1; v.knockResist = 0.1f; v.guard = 1.25f;
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
            // todos los sumos (el común, los de zona y el Ōzeki) cargan y pegan con poses que se leen desde arriba
            if (EnemyFactory.CharacterFor(archetype) == "sumo") anim.gameObject.AddComponent<SumoPoser>();
            var v = For(archetype, RegionAt(pos));
            if (v == null || CharacterKits.Attach(anim.transform, v.kit) == null) return;
            cfg.tintStrength = 0f;
            CharacterKits.Recolor(anim.transform, v.colors);
            v.ApplyStats(cfg);
            if (v.motion == null) return;
            var motion = anim.gameObject.AddComponent<VariantMotion>();
            motion.flavor = v.motion;
            motion.moveSpeed = v.speed;        // la animación al paso del suelo: sin pies que patinan
        }
    }
}
