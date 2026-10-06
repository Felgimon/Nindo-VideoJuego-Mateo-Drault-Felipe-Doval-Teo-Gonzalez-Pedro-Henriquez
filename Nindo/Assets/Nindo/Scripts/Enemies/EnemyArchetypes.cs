using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Presets de enemigos y jefes. Los nombres de estado coinciden con los AnimatorControllers
    /// generados en Assets/Nindo/Animation. Tiempos normalizados (0..1) respecto del clip.
    /// 'apex' = pose de máxima carga del arma en cada clip (de ahí sale la suelta del golpe, ver StepTimeline).
    /// </summary>
    public static class EnemyArchetypes
    {
        // apex medidos en las hojas de contacto de cada clip (el arma quieta y atrás, justo antes del tajo)
        const float NinjaApex1 = 0.50f, NinjaApex2 = 0.28f, NinjaApex3 = 0.38f;
        const float KaitoApex1 = 0.20f, KaitoApex2 = 0.15f, KaitoApex3 = 0.12f;
        // los clips del sumo casi no tienen anticipación: el apex queda 0.12 antes del golpe
        const float SumoApex1 = 0.58f, SumoApex2 = 0.48f, SumoApex3 = 0.68f, SumoApexSpecial = 0.23f;

        static AttackDef Hit(string state, float dmg, float aStart, float aEnd, float range = 2.3f, float arc = 110f,
            AttackKind kind = AttackKind.Light, float lunge = 0.8f, float telegraph = 0f, float speed = 1f, float kb = 0.6f, float apex = -1f)
        {
            return new AttackDef
            {
                name = state, state = state, damage = dmg, activeStart = aStart, activeEnd = aEnd, range = range, arc = arc,
                kind = kind, lunge = lunge, telegraph = telegraph, speed = speed, knockback = kb, apex = apex,
                hitStop = kind == AttackKind.Light ? 0.07f : 0.12f, sfx = kind == AttackKind.Light ? "enemy_swing" : "enemy_swing_heavy",
            };
        }

        public static EnemyConfig Get(string id)
        {
            switch (id)
            {
                case "ninja": return Ninja();
                case "ninja_elite": return NinjaElite();
                case "sumo": return Sumo();
                case "sumo_mountain": return SumoMountain();
                case "goro": return Goro();
                case "mizuchi": return Mizuchi();
                case "ozeki": return Ozeki();
                case "kage": return Kage();
                case "kage_clone": return KageClone();
                default:
                    Debug.LogWarning($"[Nindo] Arquetipo desconocido '{id}', uso ninja.");
                    return Ninja();
            }
        }

        // ------------------------------------------------------------------ comunes
        public static EnemyConfig Ninja()
        {
            var c = new EnemyConfig
            {
                id = "ninja", displayName = "Ninja del Clan", maxHealth = 60, runSpeed = 5.0f, walkSpeed = 2.0f,
                // aguanta el combo entero de Kaito (3 cortes) antes de cubrirse; agotado 2.4 s (ya no se le gasta el
                // desequilibrio por golpe: hasta 4 golpes o ese tiempo)
                radius = 0.42f, height = 1.7f, scale = 1f, maxImbalance = 3, exhaustedTime = 2.4f, guardTime = 1.4f,
                poiseHits = 3, preferredDistance = 3.4f, detectRadius = 10f,
                animGuard = "Guard", animCounter = "Counter", animExhausted = "Exhausted", animHit = "Hit",
                animSpotted = "Spotted", animDeath = "Death", animParried = "Hit",
            };
            var a1 = Hit("Attack1", 12, 0.6f, 0.78f, telegraph: 0.12f, apex: NinjaApex1);
            var a2 = Hit("Attack2", 12, 0.42f, 0.62f, apex: NinjaApex2);
            var a3 = Hit("Attack3", 15, 0.5f, 0.7f, kind: AttackKind.Heavy, lunge: 1.4f, kb: 1.2f, apex: NinjaApex3);
            // la estocada arranca de lejos: el aviso dura más para que se lea antes de que llegue
            var thrust = Hit("Attack3", 16, 0.5f, 0.7f, kind: AttackKind.Heavy, lunge: 3.2f, range: 2.6f, apex: NinjaApex3);
            thrust.windup = 0.7f;
            c.patterns = new[]
            {
                new AttackPattern { name = "Combo de 3", steps = new[] { a1, a2, a3 }, weight = 2f, maxRange = 2.8f },
                new AttackPattern { name = "Doble", steps = new[] { a1, a2 }, weight = 1.5f, maxRange = 2.8f },
                new AttackPattern { name = "Estocada", steps = new[] { thrust }, weight = 1f, minRange = 2.6f, maxRange = 5.5f, cooldown = 4f },
            };
            return c;
        }

        public static EnemyConfig NinjaElite()
        {
            var c = Ninja();
            c.id = "ninja_elite"; c.displayName = "Ninja de Élite";
            c.maxHealth = 90; c.runSpeed = 5.6f; c.maxImbalance = 4; c.guardTime = 1.8f; c.poiseHits = 2; c.cinematicFinisher = true;
            c.tint = new Color(0.75f, 0.18f, 0.15f); c.tintStrength = 0.55f;
            c.ScaleSteps(1.25f, 1.12f); // a1/a2 del ninja están en dos patrones: se escalan una sola vez
            var a1 = Hit("Attack1", 14, 0.6f, 0.78f, telegraph: 0.1f, speed: 1.12f, apex: NinjaApex1);
            var a2 = Hit("Attack2", 14, 0.42f, 0.62f, speed: 1.12f, apex: NinjaApex2);
            var a3 = Hit("Attack3", 18, 0.5f, 0.7f, kind: AttackKind.Heavy, lunge: 1.4f, speed: 1.1f, apex: NinjaApex3);
            var list = new System.Collections.Generic.List<AttackPattern>(c.patterns);
            list.Add(new AttackPattern { name = "Combo largo", steps = new[] { a1, a2, a1, a3 }, weight = 1.2f, maxRange = 2.8f });
            c.patterns = list.ToArray();
            return c;
        }

        public static EnemyConfig Sumo()
        {
            var c = new EnemyConfig
            {
                id = "sumo", displayName = "Luchador de Sumo", maxHealth = 150, runSpeed = 3.4f, walkSpeed = 1.6f, turnSpeed = 6f,
                radius = 0.85f, height = 2.5f, scale = 1f, maxImbalance = 2, exhaustedTime = 3.8f, guardTime = 0.8f,
                poiseHits = 4, hyperArmor = true, knockbackResist = 0.7f, preferredDistance = 3.6f, detectRadius = 11f,
                staggerTime = 0.25f, cinematicFinisher = true,
                animGuard = "Idle", animCounter = "Attack1", animExhausted = "Exhausted", animHit = "Hit",
                animSpotted = "Spotted", animDeath = "Exhausted", animParried = "Hit",
            };
            var slap1 = Hit("Attack1", 18, 0.7f, 0.9f, range: 2.8f, arc: 120, kind: AttackKind.Heavy, lunge: 0.6f, kb: 1.6f, apex: SumoApex1);
            var slap2 = Hit("Attack2", 20, 0.6f, 0.82f, range: 2.8f, arc: 130, kind: AttackKind.Heavy, lunge: 0.6f, kb: 1.6f, apex: SumoApex2);
            var stomp = Hit("Attack3", 26, 0.8f, 0.92f, range: 3.4f, arc: 360, kind: AttackKind.Heavy, lunge: 0.2f, kb: 2.2f, apex: SumoApex3);
            // embestida: el windup mínimo de un imparable (0.8 s) ya alcanza; el resto lo da el recorrido
            var charge = Hit("Special", 30, 0.35f, 0.85f, range: 2.4f, arc: 90, kind: AttackKind.Unblockable, lunge: 0f, kb: 3f, apex: SumoApexSpecial);
            charge.special = "charge"; charge.specialParam = 11f; charge.tracking = true;
            c.patterns = new[]
            {
                new AttackPattern { name = "Bofetadas", steps = new[] { slap1, slap2 }, weight = 2f, maxRange = 3.2f },
                new AttackPattern { name = "Pisotón", steps = new[] { stomp }, weight = 1f, maxRange = 3.4f, cooldown = 3f },
                new AttackPattern { name = "Embestida imparable", steps = new[] { charge }, weight = 1.4f, minRange = 3.5f, maxRange = 11f, cooldown = 5f },
            };
            return c;
        }

        public static EnemyConfig SumoMountain()
        {
            var c = Sumo();
            c.id = "sumo_mountain"; c.displayName = "Sumo de la Montaña";
            c.maxHealth = 200; c.tint = new Color(0.35f, 0.45f, 0.75f); c.tintStrength = 0.45f;
            c.ScaleSteps(1.2f, 1f);
            return c;
        }

        // ------------------------------------------------------------------ jefes
        /// <summary>Gorō, el Martillo de Kodoyama (Minijefe): lento, golpes enormes, giro imparable que lo marea.</summary>
        public static EnemyConfig Goro()
        {
            var c = new EnemyConfig
            {
                id = "goro", displayName = "Gorō", maxHealth = 520, runSpeed = 3.8f, walkSpeed = 2f, turnSpeed = 5f,
                radius = 1.0f, height = 3.2f, scale = 1f, maxImbalance = 4, exhaustedTime = 4f, guardTime = 0.6f,
                poiseHits = 5, hyperArmor = true, knockbackResist = 0.9f, preferredDistance = 4.2f, detectRadius = 30f, loseRadius = 80f,
                finisherHealth = 0.12f, attackCooldown = new Vector2(0.9f, 1.8f),
                animGuard = "Idle", animCounter = "Combo1", animExhausted = "StunSpin", animHit = "Parried",
                animSpotted = "Spotted", animDeath = "StunSpin", animParried = "Parried",
            };
            // frames de daño medidos en Blender (velocidad de la cabeza del martillo, Minijefe.fbx): antes pegaba
            // con el martillo todavía arriba (Combo1 0.19 s antes, el pisotón 0.65 s antes del impacto en el suelo)
            var c1 = Hit("Combo1", 22, 0.66f, 0.80f, range: 3.4f, arc: 130, kind: AttackKind.Heavy, lunge: 1.2f, telegraph: 0.2f, kb: 1.8f, apex: 0.58f);
            var c2 = Hit("Combo2", 24, 0.52f, 0.62f, range: 3.4f, arc: 130, kind: AttackKind.Heavy, lunge: 1.2f, kb: 1.8f, apex: 0.42f);
            var c3 = Hit("Combo3", 28, 0.63f, 0.74f, range: 3.6f, arc: 160, kind: AttackKind.Heavy, lunge: 1.0f, kb: 2.4f, apex: 0.55f);
            var slam = Hit("Heavy", 38, 0.77f, 0.80f, range: 3.4f, arc: 360, kind: AttackKind.Unblockable, lunge: 0.5f, telegraph: 0.3f, kb: 3f, apex: 0.68f);
            slam.special = "slam"; slam.specialParam = 4.6f;
            var spin = Hit("Spin", 20, 0.2f, 0.85f, range: 2.8f, arc: 360, kind: AttackKind.Unblockable, lunge: 0f, telegraph: 0.15f, kb: 2.5f, apex: 0.15f);
            spin.special = "spin"; spin.specialParam = 3.8f;
            var slam2 = slam.Clone(); slam2.specialParam = 6f; slam2.damage = 42;
            c.patterns = new[]
            {
                new AttackPattern { name = "Martillazo", steps = new[] { c1 }, weight = 1.2f, maxRange = 4f },
                new AttackPattern { name = "Doble martillazo", steps = new[] { c1, c2 }, weight = 1.5f, maxRange = 4f },
                new AttackPattern { name = "Combo completo", steps = new[] { c1, c2, c3 }, weight = 1.2f, maxRange = 4f, minPhase = 0 },
                new AttackPattern { name = "Golpe sísmico", steps = new[] { slam }, weight = 1f, maxRange = 5f, cooldown = 6f },
                new AttackPattern { name = "Torbellino", steps = new[] { spin }, weight = 1f, maxRange = 9f, cooldown = 9f, exhaustAfter = true },
                new AttackPattern { name = "Terremoto", steps = new[] { c1, slam2 }, weight = 1.3f, maxRange = 5f, cooldown = 7f, minPhase = 1 },
            };
            return c;
        }

        /// <summary>
        /// Mizuchi, el Gran Koi de la Cascada Kohan (jefe del lago): un koi espíritu de 7.5 m con el Sello del Agua clavado
        /// en el lomo. Golpes desviables con aviso dorado (mordida, aletazos, coletazo si Kaito se le pone detrás, perlas
        /// que el parry perfecto devuelve) e imparables rojos que siempre se pueden esquivar corriendo (salto del dragón,
        /// chorro). Fase 2 (55 %): corrompido, inunda la plataforma; combo de ritmo, peloteo de la perla, chorro barrido,
        /// la ola de la cascada y los pilares de agua. Fase 3 (25 %): perlas de tormenta. Los especiales los maneja
        /// MizuchiBoss. Tiempos de las hojas de contacto de Art/Characters/Mizuchi/Mizuchi.fbx.json (apex = pose cargada,
        /// activeStart = contacto); la mordida ya adelanta el cuerpo 0.6 m en el clip, la embestida del código es el resto.
        /// </summary>
        public static EnemyConfig Mizuchi()
        {
            var c = new EnemyConfig
            {
                id = "mizuchi", displayName = "Mizuchi", maxHealth = 500, runSpeed = 5f, walkSpeed = 2.4f, turnSpeed = 4.5f,
                // radio = medio cuerpo (1.95 m de ancho) más algo de aleta; altura 3 m: AimPoint a 1.65 m, el eje del cuerpo
                radius = 1.3f, height = 3f, scale = 1f, maxImbalance = 4, exhaustedTime = 3.4f, guardTime = 1.2f,
                poiseHits = 3, hyperArmor = true, knockbackResist = 0.95f, parriedRecoil = 0.4f, staggerTime = 0.3f,
                preferredDistance = 4.5f, detectRadius = 30f, loseRadius = 80f, finisherHealth = 0.12f,
                attackCooldown = new Vector2(0.8f, 1.6f),
                animGuard = "Guard", animCounter = "FinR", animExhausted = "Exhausted", animHit = "Hit",
                animSpotted = "Roar", animDeath = "Freed", animParried = "Parried",
            };
            // ---- fase 1
            var bite = Hit("Bite", 16, 0.5758f, 0.697f, range: 3.4f, arc: 70, lunge: 1.6f, telegraph: 0.22f, kb: 1f, apex: 0.4545f);
            bite.sfx = "koi_snap";
            var finL = Hit("FinL", 14, 0.5556f, 0.6667f, range: 3.3f, arc: 150, lunge: 0.9f, telegraph: 0.15f, apex: 0.4074f);
            var finR = Hit("FinR", 14, 0.4167f, 0.5417f, range: 3.3f, arc: 150, lunge: 0.7f, apex: 0.25f);
            finL.sfx = finR.sfx = "fin_whoosh";
            // el coletazo barre el disco entero desde el centro del cuerpo y no corrige la puntería: castiga quedarse detrás
            var tail = Hit("TailWhip", 22, 0.5476f, 0.7143f, range: 4.6f, arc: 360, kind: AttackKind.Heavy, lunge: 0f, telegraph: 0.28f, kb: 2.4f, apex: 0.4524f);
            tail.tracking = false; tail.sfx = "tail_crack";
            // perlas: el paso no pega, pegan las perlas (desviables; el parry perfecto las devuelve)
            var pearls = Hit("Spit", 10, 0.5556f, 0.5833f, range: 14f, arc: 60, lunge: 0f, telegraph: 0.25f, kb: 0.8f, apex: 0.4444f);
            pearls.name = "Perlas"; pearls.special = "pearls"; pearls.specialParam = 3;
            // salto del dragón: se zambulle, nada bajo el agua y salta sobre Kaito (disco rojo de 3.6 m)
            var dive = Hit("Dive", 30, 0.9f, 0.95f, range: 3.6f, arc: 360, kind: AttackKind.Unblockable, lunge: 0f, kb: 3.2f);
            dive.special = "dive"; dive.specialParam = 3.6f; dive.tracking = false;
            // chorro: apunta, se traba 0.75 s antes de disparar y la línea queda fija (un paso al costado alcanza)
            var jet = Hit("Jet", 26, 0.5455f, 0.7576f, range: 11f, arc: 20, kind: AttackKind.Unblockable, lunge: 0f, telegraph: 0.3f, kb: 2.6f, apex: 0.4848f);
            jet.special = "jet"; jet.specialParam = 11f; jet.tracking = false;
            // ---- fase 2: el torrente no retrocede con el parry (la postura igual suma) y cierra con un coletazo demorado
            var tBite = Torrente(bite); var tFinL = Torrente(finL); var tFinR = Torrente(finR); var tTail = Torrente(tail);
            tTail.telegraph = 0.45f;
            var rally = Hit("Spit", 18, 0.5556f, 0.5833f, range: 14f, arc: 60, lunge: 0f, telegraph: 0.25f, kb: 2f, apex: 0.4444f);
            rally.name = "Tama-asobi"; rally.special = "rally";
            var sweep = jet.Clone(); sweep.name = "Chorro barrido"; sweep.special = "jetsweep";
            var wave = Hit("GreatWave", 24, 0.354f, 0.396f, range: 0.1f, arc: 360, kind: AttackKind.Unblockable, lunge: 0f, kb: 3f, apex: 0.25f);
            wave.special = "greatwave"; wave.tracking = false;
            var pillars = Hit("Roar", 20, 0.3f, 0.35f, range: 0.1f, arc: 360, kind: AttackKind.Unblockable, lunge: 0f, kb: 2.5f);
            pillars.special = "pillars"; pillars.specialParam = 4; pillars.tracking = false;
            // ---- fase 3
            var storm = pearls.Clone(); storm.name = "Perlas de tormenta"; storm.special = "storm"; storm.specialParam = 5; storm.damage = 8;
            c.patterns = new[]
            {
                new AttackPattern { name = "Mordida", steps = new[] { bite }, weight = 1.6f, maxRange = 3.6f, maxAngle = 70f },
                new AttackPattern { name = "Aletazo", steps = new[] { finL, finR }, weight = 1.5f, maxRange = 3.4f, maxAngle = 110f },
                new AttackPattern { name = "Mordida y aletazo", steps = new[] { bite, finL, finR }, weight = 1.1f, maxRange = 3.6f, maxAngle = 70f, maxPhase = 0 },
                new AttackPattern { name = "Coletazo", steps = new[] { tail }, weight = 2.5f, maxRange = 4.8f, minAngle = 100f, cooldown = 4f },
                new AttackPattern { name = "Perlas del Lago", steps = new[] { pearls }, weight = 1.2f, minRange = 6f, maxRange = 14f, cooldown = 5f, maxPhase = 0 },
                new AttackPattern { name = "Salto del Dragón", steps = new[] { dive }, weight = 1f, maxRange = 30f, cooldown = 12f },
                new AttackPattern { name = "Chorro", steps = new[] { jet }, weight = 0.9f, minRange = 4f, maxRange = 11f, cooldown = 9f, maxPhase = 0 },
                new AttackPattern { name = "Torrente", steps = new[] { tBite, tFinL, tFinR, tTail }, weight = 1.6f, maxRange = 3.6f, maxAngle = 70f, minPhase = 1 },
                new AttackPattern { name = "Tama-asobi", steps = new[] { rally }, weight = 1f, minRange = 6f, maxRange = 14f, cooldown = 14f, minPhase = 1 },
                new AttackPattern { name = "Chorro barrido", steps = new[] { sweep }, weight = 1f, minRange = 4f, maxRange = 9f, cooldown = 8f, minPhase = 1 },
                new AttackPattern { name = "Ola de la Cascada", steps = new[] { wave }, weight = 0.9f, maxRange = 30f, cooldown = 15f, minPhase = 1 },
                new AttackPattern { name = "Pilares", steps = new[] { pillars }, weight = 0.8f, maxRange = 30f, cooldown = 20f, minPhase = 1 },
                new AttackPattern { name = "Perlas de tormenta", steps = new[] { storm }, weight = 1f, minRange = 6f, maxRange = 14f, cooldown = 6f, minPhase = 2 },
            };
            return c;
        }

        static AttackDef Torrente(AttackDef a)
        {
            var t = a.Clone();
            t.name = "Torrente " + a.name;
            t.noRecoil = true;
            return t;
        }

        /// <summary>Ōzeki, el Gran Campeón (bosque de bambú): sumo gigante, embestidas y pisotones.</summary>
        public static EnemyConfig Ozeki()
        {
            var c = Sumo();
            c.id = "ozeki"; c.displayName = "Ōzeki"; c.maxHealth = 560; c.scale = 1.35f; c.maxImbalance = 3;
            c.detectRadius = 30; c.loseRadius = 80; c.finisherHealth = 0.12f; c.exhaustedTime = 4.5f;
            c.tint = new Color(0.55f, 0.15f, 0.12f); c.tintStrength = 0.35f;
            var slap1 = Hit("Attack1", 22, 0.7f, 0.9f, range: 3.2f, arc: 130, kind: AttackKind.Heavy, lunge: 0.8f, kb: 2f, apex: SumoApex1);
            var slap2 = Hit("Attack2", 24, 0.6f, 0.82f, range: 3.2f, arc: 130, kind: AttackKind.Heavy, lunge: 0.8f, kb: 2f, apex: SumoApex2);
            var stomp = Hit("Attack3", 30, 0.8f, 0.92f, range: 3.6f, arc: 360, kind: AttackKind.Unblockable, lunge: 0.2f, telegraph: 0.25f, kb: 3f, apex: SumoApex3);
            stomp.special = "slam"; stomp.specialParam = 5f;
            var charge = Hit("Special", 32, 0.35f, 0.85f, range: 2.6f, arc: 90, kind: AttackKind.Unblockable, lunge: 0f, kb: 3.5f, apex: SumoApexSpecial);
            charge.special = "charge"; charge.specialParam = 13f;
            c.patterns = new[]
            {
                new AttackPattern { name = "Bofetadas", steps = new[] { slap1, slap2 }, weight = 2f, maxRange = 3.8f },
                new AttackPattern { name = "Triple bofetada", steps = new[] { slap1, slap2, slap1 }, weight = 1.2f, maxRange = 3.8f, minPhase = 1 },
                new AttackPattern { name = "Pisotón sísmico", steps = new[] { stomp }, weight = 1f, maxRange = 5f, cooldown = 5f },
                new AttackPattern { name = "Embestida", steps = new[] { charge }, weight = 1.3f, minRange = 4f, maxRange = 16f, cooldown = 4f },
                new AttackPattern { name = "Doble embestida", steps = new[] { charge, charge }, weight = 1f, minRange = 4f, maxRange = 16f, cooldown = 8f, minPhase = 1 },
            };
            return c;
        }

        /// <summary>Kage, la Sombra (jefe final): espejo de Kaito. Rápido, desvía mucho, se teletransporta y crea clones.</summary>
        public static EnemyConfig Kage()
        {
            var c = new EnemyConfig
            {
                id = "kage", displayName = "Kage", maxHealth = 600, runSpeed = 6.8f, walkSpeed = 2.6f, turnSpeed = 14f,
                radius = 0.4f, height = 1.6f, scale = 1.05f, maxImbalance = 5, exhaustedTime = 2.6f, guardTime = 1.8f,
                poiseHits = 1, preferredDistance = 3.2f, detectRadius = 30f, loseRadius = 80f, finisherHealth = 0.1f,
                attackCooldown = new Vector2(0.35f, 1.0f), windupScale = 0.873f,
                tint = new Color(0.12f, 0.08f, 0.2f), tintStrength = 0.8f,
                animGuard = "ParryStance", animCounter = "ParrySuccess", animExhausted = "Blocked", animHit = "Hit",
                animSpotted = "Blocked", animDeath = "Hit", animParried = "Blocked",
            };
            // usa los clips de Kaito (0.3-0.6 s): casi no tienen anticipación, la pone StepTimeline. Kage es el más
            // rápido del juego (windup 0.48 s / 0.38 s encadenado, windupScale) pero el aviso sigue siendo exacto
            var a1 = Hit("Attack1", 14, 0.3f, 0.6f, range: 2.4f, speed: 0.8f, apex: KaitoApex1);
            var a2 = Hit("Attack2", 14, 0.25f, 0.6f, range: 2.4f, speed: 0.8f, apex: KaitoApex2);
            var a3 = Hit("Attack3", 20, 0.22f, 0.45f, range: 2.7f, kind: AttackKind.Heavy, lunge: 1.8f, speed: 0.85f, kb: 1.6f, apex: KaitoApex3);
            var tp = Hit("Dash", 0, 0.2f, 0.25f, lunge: 0f); tp.special = "teleport"; tp.specialParam = 2.2f;
            var ws = Hit("Attack3", 30, 0.3f, 0.35f, kind: AttackKind.Unblockable, lunge: 0f, kb: 2f, apex: KaitoApex3);
            ws.special = "windslash"; ws.specialParam = 10f;
            var clones = Hit("ParrySuccess", 0, 0.5f, 0.55f, lunge: 0f); clones.special = "clones"; clones.specialParam = 2;
            c.patterns = new[]
            {
                new AttackPattern { name = "Espejo", steps = new[] { a1, a2, a3 }, weight = 2f, maxRange = 3f },
                new AttackPattern { name = "Rápido", steps = new[] { a1, a2 }, weight = 1.5f, maxRange = 3f },
                new AttackPattern { name = "Sombra", steps = new[] { tp, a1, a2, a3 }, weight = 1.2f, maxRange = 14f, cooldown = 5f },
                new AttackPattern { name = "Corte del Vacío", steps = new[] { ws }, weight = 1.1f, minRange = 3f, maxRange = 12f, cooldown = 6f },
                new AttackPattern { name = "Clones", steps = new[] { clones }, weight = 1f, maxRange = 20f, cooldown = 22f, minPhase = 1 },
                new AttackPattern { name = "Furia sombría", steps = new[] { a1, a2, a1, a2, a3 }, weight = 1.3f, maxRange = 3f, minPhase = 1 },
            };
            return c;
        }

        public static EnemyConfig KageClone()
        {
            var c = Kage();
            c.id = "kage_clone"; c.displayName = "Sombra"; c.maxHealth = 1; c.poiseHits = 99; c.guardTime = 0.1f;
            c.tint = new Color(0.25f, 0.1f, 0.4f); c.tintStrength = 0.9f; c.scale = 1f; c.detectRadius = 40f;
            c.windupScale = 1f;   // los clones son más lentos que Kage: se distinguen por el ritmo
            var a1 = Hit("Attack1", 10, 0.3f, 0.6f, range: 2.4f, speed: 0.8f, apex: KaitoApex1);
            var a3 = Hit("Attack3", 12, 0.22f, 0.45f, range: 2.7f, lunge: 1.6f, speed: 0.8f, apex: KaitoApex3);
            c.patterns = new[] { new AttackPattern { name = "Eco", steps = new[] { a1, a3 }, weight = 1f, maxRange = 3f } };
            return c;
        }
    }
}
