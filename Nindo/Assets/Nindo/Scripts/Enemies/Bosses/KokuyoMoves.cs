using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Golpes y patrones de Kokuyō (jefe final, arquetipo "kage") y de su sombra arrancada, Kage. Los tiempos de cada
    /// golpe salen de KokuyoTimings (lo que mide el build de Blender), así el aviso, la sombra y el tajo no se despegan
    /// del clip. Contrato de lectura (judge_final):
    ///  * DÓNDE: el aviso en el suelo desde que arranca el paso (dorado = parry, rojo con zona = dash).
    ///  * CUÁNDO: un único "¡ahora!" a 0.36 s del golpe (GoLead): el filo destella, suena el hyōshigi y, en el Acto 1,
    ///    la sombra golpea. Desde ahí deja de apuntar: correrse sirve.
    ///  * cada imparable deja una ventana de castigo; nunca pegan el cuerpo y la sombra a menos de 0.9 s.
    /// La pausa en el apex (la pose del aviso) se acorta por acto: 0.42 s, 0.30 s, 0.22 s.
    /// </summary>
    public static class KokuyoMoves
    {
        /// <summary>El "¡ahora!": el filo destella, la sombra golpea y la puntería se traba (s antes del impacto).</summary>
        public const float GoLead = 0.36f;
        /// <summary>Pausa en el apex de los desviables por acto (1..3).</summary>
        static readonly float[] ParryHold = { 0f, 0.42f, 0.30f, 0.22f };
        /// <summary>Los imparables ya tienen una anticipación larga (0.9-1 s): solo un respiro en el apex.</summary>
        static readonly float[] DodgeHold = { 0f, 0.15f, 0.08f, 0.08f };
        /// <summary>StepTimeline.MinWindup multiplica por 0.9 desde la fase 1 (Actos 2 y 3): se compensa para que las
        /// pausas de arriba sean las que se ven.</summary>
        const float PhaseWindupMul = 0.9f;

        public const string Cut = "k_cut", Thrust = "k_thrust", Sweep = "k_sweep", Rift = "k_rift", Sink = "k_sink", NoHit = "k_none";
        /// <summary>Kage, la sombra suelta: se desliza bajo Kaito y estalla / cruza el patio.</summary>
        public const string Nui = "kage_nui", Watari = "kage_watari";

        /// <summary>Grieta de obsidiana del Rompecascos: carril de 14 x 2 m que avanza a 28 m/s desde el golpe.</summary>
        public const float RiftLength = 14f, RiftHalfWidth = 1.0f, RiftSpeed = 28f;
        public const float RiftDamage = 26f, RiftKnockback = 2.5f;
        /// <summary>Ichimonji: dentro de este radio la hoja pasa por encima de la cabeza de Kaito (la empuñadura va a
        /// 1.9 m y la punta baja a 0.97 m: a menos de ~2 m del centro la hoja corta arriba de 1.5 m).</summary>
        public const float SweepCore = 1.65f;

        static readonly Dictionary<string, KokuyoClip> clips = new Dictionary<string, KokuyoClip>
        {
            { "Kesagiri", KokuyoTimings.Kesagiri }, { "Gyakugiri", KokuyoTimings.Gyakugiri }, { "Tsuki", KokuyoTimings.Tsuki },
            { "TsukiRecover", KokuyoTimings.TsukiRecover }, { "Ichimonji", KokuyoTimings.Ichimonji }, { "KabutoWari", KokuyoTimings.KabutoWari },
            { "ShadowSink", KokuyoTimings.ShadowSink }, { "ShadowEmerge", KokuyoTimings.ShadowEmerge }, { "RecoverL", KokuyoTimings.RecoverL },
            { "RecoverHR", KokuyoTimings.RecoverHR },
        };

        /// <summary>Tiempos del clip de un paso (null si no es de Kokuyō).</summary>
        public static KokuyoClip ClipOf(AttackDef a) => a != null && clips.TryGetValue(a.state, out var c) ? c : null;

        // ------------------------------------------------------------------ golpes
        /// <summary>
        /// Golpe con sus propios tiempos (sin la curva genérica de los comunes). El avance del cuerpo lo hace el
        /// jefe con travel_m del clip (lunge = 0: con la embestida lineal los pies patinan). 'range' es lo más lejos que
        /// puede llegar (hoja + avance entero): lo usan el aviso de los bots y el tutorial; el golpe real se mide con
        /// el alcance de la hoja desde donde está en el impacto.
        /// </summary>
        static AttackDef K(KokuyoClip c, string name, float dmg, AttackKind kind, float arc, float kb, float hold, int act, string special)
        {
            float natural = c.Apex * c.Seconds / 0.85f + (c.Contact - c.Apex) * c.Seconds / c.ReleaseRate;
            float windup = natural + hold;
            if (act >= 2) windup /= PhaseWindupMul;
            float travel = c.Travel != null ? c.Travel[c.Travel.Length - 1] : 0f;
            return new AttackDef
            {
                name = name, state = c.State, damage = dmg, kind = kind, arc = arc, knockback = kb,
                range = c.Reach + travel, activeStart = c.Contact, activeEnd = c.ActiveEnd, apex = c.Apex, releaseRate = c.ReleaseRate,
                windup = windup, lunge = 0f, tracking = false, hitStop = 0.12f, shake = 0.4f, imbalance = 1f,
                sfx = "enemy_swing_heavy", special = special,
            };
        }

        /// <summary>Paso sin golpe (recuperación, hundirse en la sombra): el clip a su velocidad.</summary>
        static AttackDef R(KokuyoClip c, string special = NoHit) => new AttackDef
        {
            name = c.State, state = c.State, damage = 0f, activeStart = 0.02f, activeEnd = 0.02f, apex = 0f, lunge = 0f,
            tracking = false, special = special,
        };

        /// <summary>Los golpes de un acto (1..3): cada acto tiene sus propias pausas en el apex.</summary>
        sealed class Set
        {
            public AttackDef kesa, gyaku, tsuki, ichi, kabuto, emerge;
            public Set(int act)
            {
                float ph = ParryHold[act], dh = DodgeHold[act];
                kesa = K(KokuyoTimings.Kesagiri, "Corte del Monje", 24, AttackKind.Heavy, 120f, 1.6f, ph, act, Cut);
                gyaku = K(KokuyoTimings.Gyakugiri, "Luna Ascendente", 22, AttackKind.Heavy, 120f, 1.4f, ph, act, Cut);
                // la estocada ya tiene la anticipación más larga del juego (0.86 s de recogida + 0.42 de salto): media pausa
                tsuki = K(KokuyoTimings.Tsuki, "Colmillo", 28, AttackKind.Heavy, 40f, 2.4f, ph * 0.5f, act, Thrust);
                ichi = K(KokuyoTimings.Ichimonji, "Horizonte", 34, AttackKind.Unblockable, 240f, 3.0f, dh, act, Sweep);
                kabuto = K(KokuyoTimings.KabutoWari, "Rompecascos", 38, AttackKind.Unblockable, 50f, 2.5f, dh, act, Rift);
                emerge = K(KokuyoTimings.ShadowEmerge, "Paso de Sombra", 24, AttackKind.Heavy, 140f, 1.6f, ph, act, Cut);
            }
        }

        static readonly AttackDef recoverL = R(KokuyoTimings.RecoverL), recoverHR = R(KokuyoTimings.RecoverHR),
            tsukiRecover = R(KokuyoTimings.TsukiRecover), sink = R(KokuyoTimings.ShadowSink, Sink);

        static AttackPattern P(string name, float weight, float maxRange, float cooldown, params AttackDef[] steps) =>
            new AttackPattern { name = name, steps = steps, weight = weight, maxRange = maxRange, cooldown = cooldown };

        /// <summary>
        /// Patrones de cada acto. Acto 1 enseña de a una cosa; el 2 suma la Escuela del Abuelo (corte, corte, estocada:
        /// el mismo ritmo del combo de Kaito, más lento) y el Paso de Sombra; el 3 encadena el Desfile (cuatro parries y
        /// un dash) y la Media Luna. Mezcla: ~70 % desviables, ~30 % imparables.
        /// </summary>
        public static AttackPattern[] Act(int act)
        {
            var s = new Set(Mathf.Clamp(act, 1, 3));
            var monje = P("Corte del Monje", 1.6f, 5.0f, 0f, s.kesa, recoverL);
            var doble = P("Luna Doble", 1.8f, 5.0f, 0f, s.kesa, s.gyaku, recoverHR);
            var colmillo = P("Colmillo", 1.2f, 8.5f, 4f, s.tsuki, tsukiRecover); colmillo.minRange = 4f;
            var horizonte = P("Horizonte", 1.0f, 5.5f, 7f, s.ichi);
            var rompe = P("Rompecascos", 0.9f, 10f, 9f, s.kabuto); rompe.minRange = 2.5f;
            if (act <= 1) return new[] { monje, doble, colmillo, horizonte, rompe };
            var escuela = P("Escuela del Abuelo", 1.6f, 5.0f, 0f, s.kesa, s.gyaku, s.tsuki, tsukiRecover);
            var paso = P("Paso de Sombra", 1.2f, 16f, 8f, sink, s.emerge, recoverHR);
            if (act == 2)
            {
                doble.weight = 1.4f; colmillo.weight = 1.0f; horizonte.weight = 0.8f; rompe.weight = 0.8f;
                return new[] { doble, colmillo, horizonte, rompe, escuela, paso };
            }
            doble.weight = 1.0f; colmillo.weight = 0.8f; horizonte.weight = 0.6f; rompe.weight = 0.6f; escuela.weight = 1.2f; paso.weight = 1.0f;
            var desfile = P("Desfile de los Cien Demonios", 1.5f, 5.0f, 10f, s.kesa, s.gyaku, s.kesa, s.tsuki, s.kabuto);
            var media = P("Media Luna", 1.2f, 5.0f, 6f, s.gyaku, s.ichi);
            return new[] { doble, colmillo, horizonte, rompe, escuela, paso, desfile, media };
        }

        /// <summary>Contraataque (Kaito le pegó dos veces a la guardia): el Counter termina en LOW_L y sigue un gyakugiri.</summary>
        public static AttackPattern Counter(int act)
        {
            var s = new Set(Mathf.Clamp(act, 1, 3));
            return P("Contra", 1f, 99f, 0f, s.gyaku, recoverHR);
        }

        /// <summary>El Último Desfile (10 %): cinco golpes con la pausa más corta y, al terminar, de rodillas sí o sí.</summary>
        public static AttackPattern LastParade()
        {
            var s = new Set(3);
            var p = P("Último Desfile", 1f, 5.0f, 0f, s.kesa, s.gyaku, s.kesa, s.gyaku, s.tsuki);
            p.exhaustAfter = true;
            return p;
        }

        // ------------------------------------------------------------------ configs
        /// <summary>Kokuyō, Señor del Clan Kurokage. Patrones del Acto 1 (los otros los pone KokuyoBoss al cambiar de acto).</summary>
        public static EnemyConfig Kokuyo()
        {
            return new EnemyConfig
            {
                id = "kage", displayName = "Kokuyō", maxHealth = 900, runSpeed = 3.0f, walkSpeed = 1.8f, turnSpeed = 4.5f,
                radius = 1.1f, height = 4.2f, scale = 1f, tintStrength = 0f,
                maxImbalance = 5, exhaustedTime = KokuyoTimings.Kneel.Seconds, exhaustedDamageMul = 1.3f, guardTime = 0.8f,
                poiseHits = 4, hyperArmor = true, knockbackResist = 0.95f, staggerTime = 0.3f, parriedRecoil = 0.55f,
                preferredDistance = 4.6f, detectRadius = 30f, loseRadius = 80f,
                // la ejecución solo se habilita de rodillas en la última resistencia (KokuyoBoss la abre y la cierra)
                finisherHealth = 0f, attackCooldown = new Vector2(0.7f, 1.4f), cinematicFinisher = true,
                animGuard = "Guard", animCounter = "Counter", animExhausted = "Kneel", animHit = "Flinch",
                animSpotted = "Roar", animDeath = "Defeat", animParried = "Parried",
                patterns = Act(1),
            };
        }

        /// <summary>Kage, la sombra arrancada (Acto 2): no se puede fijar ni cortar; solo las habilidades la clavan.</summary>
        public static EnemyConfig Shadow()
        {
            var nui = new AttackDef
            {
                name = "Kage-nui", state = "", damage = 18, kind = AttackKind.Unblockable, knockback = 2.2f, lunge = 0f, tracking = false,
                activeStart = 0.5f, activeEnd = 0.6f, apex = 0.35f, hitStop = 0.1f, sfx = "kokuyo_whisper", special = Nui,
            };
            var watari = new AttackDef
            {
                name = "Kage-watari", state = "", damage = 20, kind = AttackKind.Unblockable, knockback = 2.4f, lunge = 0f, tracking = false,
                activeStart = 0.5f, activeEnd = 0.6f, apex = 0.35f, hitStop = 0.1f, sfx = "kokuyo_whisper", special = Watari,
                windup = 0.6f,
            };
            return new EnemyConfig
            {
                id = "kage_shadow", displayName = "Kage", maxHealth = 1, runSpeed = 7f, walkSpeed = 7f, turnSpeed = 8f,
                radius = 0.8f, height = 4.2f, scale = 1f, maxImbalance = 99, detectRadius = 0f, finisherHealth = 0f,
                attackCooldown = new Vector2(2.5f, 4f),
                patterns = new[]
                {
                    new AttackPattern { name = "Kage-nui", steps = new[] { nui }, weight = 2f, maxRange = 99f },
                    new AttackPattern { name = "Kage-watari", steps = new[] { watari }, weight = 1f, maxRange = 99f },
                },
            };
        }
    }
}
