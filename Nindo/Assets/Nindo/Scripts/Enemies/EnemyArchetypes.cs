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
        // apex = fin de la pausa del aviso y activeStart = cuadro de contacto de los clips nuevos (TeamAnims/*Anims.fbx.json,
        // 'normalized': Tools/Blender/anim/build_team_anims.py falla si estos números no coinciden con el clip)
        const float NinjaApex1 = 0.50f, NinjaApex2 = 0.318f, NinjaApex3 = 0.382f, NinjaApexThrust = 0.275f;
        const float SumoApex1 = 0.556f, SumoApex2 = 0.407f, SumoApex3 = 0.571f, SumoApexSpecial = 0.233f;

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
                animSpotted = "Spotted", animDeath = "Death", animParried = "Parried", deathClipFalls = true,
            };
            var a1 = Hit("Attack1", 12, 0.583f, 0.75f, telegraph: 0.12f, apex: NinjaApex1);
            var a2 = Hit("Attack2", 12, 0.455f, 0.636f, apex: NinjaApex2);
            var a3 = Hit("Attack3", 15, 0.5f, 0.618f, kind: AttackKind.Heavy, lunge: 1.4f, kb: 1.2f, apex: NinjaApex3);
            // la estocada arranca de lejos con su propio clip (se lanza volando): el aviso dura más para que se lea
            var thrust = Hit("Thrust", 16, 0.525f, 0.625f, kind: AttackKind.Heavy, lunge: 3.2f, range: 2.6f, apex: NinjaApexThrust);
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
            var a1 = Hit("Attack1", 14, 0.583f, 0.75f, telegraph: 0.1f, speed: 1.12f, apex: NinjaApex1);
            var a2 = Hit("Attack2", 14, 0.455f, 0.636f, speed: 1.12f, apex: NinjaApex2);
            var a3 = Hit("Attack3", 18, 0.5f, 0.618f, kind: AttackKind.Heavy, lunge: 1.4f, speed: 1.1f, apex: NinjaApex3);
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
                animSpotted = "Spotted", animDeath = "Death", animParried = "Parried", deathClipFalls = true,
            };
            var slap1 = Hit("Attack1", 18, 0.667f, 0.815f, range: 2.8f, arc: 120, kind: AttackKind.Heavy, lunge: 0.6f, kb: 1.6f, apex: SumoApex1);
            var slap2 = Hit("Attack2", 20, 0.593f, 0.741f, range: 2.8f, arc: 130, kind: AttackKind.Heavy, lunge: 0.6f, kb: 1.6f, apex: SumoApex2);
            var stomp = Hit("Attack3", 26, 0.643f, 0.738f, range: 3.4f, arc: 360, kind: AttackKind.Heavy, lunge: 0.2f, kb: 2.2f, apex: SumoApex3);
            // embestida: el windup mínimo de un imparable (0.8 s) ya alcanza; el resto lo da el recorrido (la fase
            // activa del clip es la carrera, que Enemy estira lo que dura el carril)
            var charge = Hit("Special", 30, 0.3f, 0.7f, range: 2.4f, arc: 90, kind: AttackKind.Unblockable, lunge: 0f, kb: 3f, apex: SumoApexSpecial);
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
            SumoMountainMoves(c);     // es el sumo de la montaña: pelea como tal aunque aparezca en otro lado
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
                animGuard = "Idle", animCounter = "Combo1", animExhausted = "StunSpin", animHit = "Hit",
                animSpotted = "Spotted", animDeath = "Death", animParried = "Parried", deathClipFalls = true,
            };
            // contacto = activeStart de los clips nuevos (TeamAnims/GoroAnims.fbx): la cabeza del martillo llega en ese
            // cuadro; el golpe sísmico pega al aterrizar del salto, no al despegar
            var c1 = Hit("Combo1", 22, 0.667f, 0.778f, range: 3.4f, arc: 130, kind: AttackKind.Heavy, lunge: 1.2f, telegraph: 0.2f, kb: 1.8f, apex: 0.583f);
            var c2 = Hit("Combo2", 24, 0.583f, 0.667f, range: 3.4f, arc: 130, kind: AttackKind.Heavy, lunge: 1.2f, kb: 1.8f, apex: 0.5f);
            var c3 = Hit("Combo3", 28, 0.633f, 0.733f, range: 3.6f, arc: 160, kind: AttackKind.Heavy, lunge: 1.0f, kb: 2.4f, apex: 0.533f);
            var slam = Hit("Heavy", 38, 0.667f, 0.7f, range: 3.4f, arc: 360, kind: AttackKind.Unblockable, lunge: 0.5f, telegraph: 0.3f, kb: 3f, apex: 0.533f);
            slam.special = "slam"; slam.specialParam = 4.6f;
            var spin = Hit("Spin", 20, 0.288f, 0.848f, range: 2.8f, arc: 360, kind: AttackKind.Unblockable, lunge: 0f, telegraph: 0.15f, kb: 2.5f, apex: 0.242f);
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
        /// activeStart = contacto); la mordida ya adelanta el cuerpo 0.6 m en el clip.
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
                // contraataque: muestra el flanco (Guard) antes del golpe; con FinR barría con la aleta sin pegar
                animGuard = "Guard", animCounter = "Guard", animExhausted = "Exhausted", animHit = "Hit",
                animSpotted = "Roar", animDeath = "Freed", animParried = "Parried",
            };
            // ---- fase 1
            // embestidas cortas: el tope de Enemy se mide con el radio del cuerpo (1.3) y la boca está 2.9 m adelante;
            // con más avance el hocico atravesaba a Kaito
            var bite = Hit("Bite", 16, 0.5758f, 0.697f, range: 3.4f, arc: 70, lunge: 0.6f, telegraph: 0.22f, kb: 1f, apex: 0.4545f);
            bite.sfx = "koi_snap";
            var finL = Hit("FinL", 14, 0.5556f, 0.6667f, range: 3.3f, arc: 150, lunge: 0.5f, telegraph: 0.15f, apex: 0.4074f);
            var finR = Hit("FinR", 14, 0.4167f, 0.5417f, range: 3.3f, arc: 150, lunge: 0.4f, apex: 0.25f);
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
            jet.special = "jet"; jet.specialParam = 11f; jet.tracking = false; jet.sfx = "jet_fire";
            // ---- fase 2: el torrente no retrocede con el parry (la postura igual suma) y cierra con un coletazo demorado
            var tBite = Torrente(bite); var tFinL = Torrente(finL); var tFinR = Torrente(finR); var tTail = Torrente(tail);
            tTail.telegraph = 0.45f;
            var rally = Hit("Spit", 18, 0.5556f, 0.5833f, range: 14f, arc: 60, lunge: 0f, telegraph: 0.25f, kb: 2f, apex: 0.4444f);
            rally.name = "Tama-asobi"; rally.special = "rally";
            // el barrido se traba 1 s antes (abanico más ancho que la línea): con más aviso la mira vive ~0.4 s antes de
            // trabarse y se lee "apunta, se traba" como en el chorro (con 0.3 la mira duraba 0.1-0.2 s)
            var sweep = jet.Clone(); sweep.name = "Chorro barrido"; sweep.special = "jetsweep"; sweep.telegraph = 0.7f;
            var wave = Hit("GreatWave", 24, 0.354f, 0.396f, range: 0.1f, arc: 360, kind: AttackKind.Unblockable, lunge: 0f, kb: 3f, apex: 0.25f);
            wave.special = "greatwave"; wave.tracking = false;
            var pillars = Hit("Roar", 20, 0.3f, 0.35f, range: 0.1f, arc: 360, kind: AttackKind.Unblockable, lunge: 0f, kb: 2.5f);
            pillars.special = "pillars"; pillars.specialParam = 4; pillars.tracking = false;
            // ---- fase 3
            var storm = pearls.Clone(); storm.name = "Perlas de tormenta"; storm.special = "storm"; storm.specialParam = 5; storm.damage = 8;
            // los especiales grandes piden 2 m o más: el contraataque (Enemy.Counter elige con distancia 1) es siempre un golpe corto
            c.patterns = new[]
            {
                new AttackPattern { name = "Mordida", steps = new[] { bite }, weight = 1.6f, maxRange = 3.6f, maxAngle = 70f },
                new AttackPattern { name = "Aletazo", steps = new[] { finL, finR }, weight = 1.5f, maxRange = 3.4f, maxAngle = 110f },
                new AttackPattern { name = "Mordida y aletazo", steps = new[] { bite, finL, finR }, weight = 1.1f, maxRange = 3.6f, maxAngle = 70f, maxPhase = 0 },
                new AttackPattern { name = "Coletazo", steps = new[] { tail }, weight = 2.5f, maxRange = 4.8f, minAngle = 100f, cooldown = 4f },
                new AttackPattern { name = "Perlas del Lago", steps = new[] { pearls }, weight = 1.2f, minRange = 6f, maxRange = 14f, cooldown = 5f, maxPhase = 0 },
                new AttackPattern { name = "Salto del Dragón", steps = new[] { dive }, weight = 1f, minRange = 2f, maxRange = 30f, cooldown = 12f },
                new AttackPattern { name = "Chorro", steps = new[] { jet }, weight = 0.9f, minRange = 4f, maxRange = 11f, maxAngle = 35f, cooldown = 9f, maxPhase = 0 },
                new AttackPattern { name = "Torrente", steps = new[] { tBite, tFinL, tFinR, tTail }, weight = 1.6f, maxRange = 3.6f, maxAngle = 70f, minPhase = 1 },
                new AttackPattern { name = "Tama-asobi", steps = new[] { rally }, weight = 1f, minRange = 6f, maxRange = 14f, cooldown = 14f, minPhase = 1 },
                new AttackPattern { name = "Chorro barrido", steps = new[] { sweep }, weight = 1f, minRange = 4f, maxRange = 9f, maxAngle = 35f, cooldown = 8f, minPhase = 1 },
                new AttackPattern { name = "Ola de la Cascada", steps = new[] { wave }, weight = 0.9f, minRange = 2f, maxRange = 30f, cooldown = 15f, minPhase = 1 },
                new AttackPattern { name = "Pilares", steps = new[] { pillars }, weight = 0.8f, minRange = 2f, maxRange = 30f, cooldown = 20f, minPhase = 1 },
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

        /// <summary>
        /// Ōzeki, el Gran Campeón del Bambú (Enemies/Bosses/OzekiBoss.cs): un yokozuna que se lee por colores.
        /// Dorado: harite y tsuppari (bofetadas en ritmo, de a una mano). Rojo: agarre (los brazos abiertos), shiko
        /// (la pierna arriba: onda por el piso hasta 8 m) y tachiai (agachado con los puños abajo: embestida que el
        /// bambú del claro frena). Fase 2 (50 %): más rápido, la tsuna encendida, la sal como respiro y combos largos.
        /// Los nombres de los golpes eligen la pose de SumoPoser (la carga y el golpe que se ven desde arriba).
        /// </summary>
        public static EnemyConfig Ozeki()
        {
            var c = Sumo();
            // 760: con 560 el bot de pruebas lo terminaba en 22 s (las pausas de la sal y el agarre esquivado regalan
            // golpes libres) y la fase 2 casi no llegaba a verse; Kokuyō, con 900 y sus actos, dura ~2 min
            c.id = "ozeki"; c.displayName = "Ōzeki"; c.maxHealth = 760; c.scale = 1.35f; c.maxImbalance = 4;
            c.detectRadius = 30; c.loseRadius = 80; c.finisherHealth = 0.12f; c.exhaustedTime = 4f; c.guardTime = 0.8f;
            c.runSpeed = 3.8f; c.walkSpeed = 1.8f; c.turnSpeed = 6.5f; c.preferredDistance = 4.4f;
            c.attackCooldown = new Vector2(0.6f, 1.3f);
            // sin tinte: lo viste su kit (tsuna, delantal violeta, abanico dorado)
            c.tint = Color.white; c.tintStrength = 0f;
            var hD = Hit("Attack1", 16, 0.667f, 0.815f, range: 3.0f, arc: 120, kind: AttackKind.Heavy, lunge: 0.9f, telegraph: 0.05f, kb: 2f, apex: SumoApex1);
            hD.name = "Harite D";
            var hI = Hit("Attack2", 16, 0.593f, 0.741f, range: 3.0f, arc: 120, kind: AttackKind.Heavy, lunge: 0.9f, kb: 2f, apex: SumoApex2);
            hI.name = "Harite I";
            // la última del tsuppari furioso se demora un tercio de segundo: el que aprieta por ritmo se adelanta
            var hLate = hD.Clone(); hLate.telegraph = 0.32f;
            // agarre: imparable de cerca (solo dash, o salir de adelante cuando abre los brazos)
            var grab = Hit("Attack2", 26, 0.593f, 0.741f, range: 3.0f, arc: 100, kind: AttackKind.Unblockable, lunge: 1.5f, telegraph: 0.1f, kb: 3.5f, apex: SumoApex2);
            grab.special = "grab"; grab.name = "Agarre";
            // shiko: la pierna sube ~1.1 s (el clip del pisotón) y la onda se abre a 7 m/s hasta 8 m
            var shikoD = Hit("Attack3", 22, 0.643f, 0.738f, range: 3.0f, arc: 360, kind: AttackKind.Unblockable, lunge: 0f, telegraph: 0.05f, kb: 2.6f, apex: SumoApex3);
            shikoD.special = "shiko"; shikoD.specialParam = 8f; shikoD.tracking = false; shikoD.name = "Shiko D";
            var shikoI = shikoD.Clone(); shikoI.name = "Shiko I";
            // tachiai: 0.5 s agachándose y 0.45 s quieto con los puños en el piso; después 13 m/s por un carril fijo.
            // Desde 6-10.5 m: más cerca no hay tiempo de salir corriendo del carril; más lejos arranca fuera de cuadro
            var tachiai = Hit("Special", 28, 0.3f, 0.7f, range: 2.6f, arc: 90, kind: AttackKind.Unblockable, lunge: 0f, telegraph: 0.2f, kb: 4f, apex: SumoApexSpecial);
            tachiai.special = "tachiai"; tachiai.specialParam = 13f; tachiai.tracking = true; tachiai.name = "Tachiai";
            // la sal (fase 2): no pega; al terminar queda abierto (OzekiBoss.ComboEnd)
            var salt = Hit("Spotted", 0, 0.55f, 0.6f, lunge: 0f, telegraph: 0.75f);
            salt.special = "salt"; salt.tracking = false; salt.name = "Shio";
            c.patterns = new[]
            {
                new AttackPattern { name = "Harite", steps = new[] { hD, hI }, weight = 2f, maxRange = 4.2f },
                new AttackPattern { name = "Tsuppari", steps = new[] { hD, hI, hD }, weight = 1.4f, maxRange = 4.2f, cooldown = 3f },
                new AttackPattern { name = "Harite y agarre", steps = new[] { hD, grab }, weight = 1.1f, maxRange = 4.2f, cooldown = 6f },
                new AttackPattern { name = "Agarre", steps = new[] { grab }, weight = 0.7f, maxRange = 3.8f, cooldown = 7f },
                new AttackPattern { name = "Shiko", steps = new[] { shikoD }, weight = 1f, maxRange = 6.5f, cooldown = 7f },
                new AttackPattern { name = "Tachiai", steps = new[] { tachiai }, weight = 1.6f, minRange = 6f, maxRange = 10.5f, cooldown = 4f },
                new AttackPattern { name = "Tsuppari furioso", steps = new[] { hD, hI, hD, hI, hLate }, weight = 1.3f, maxRange = 4.2f, cooldown = 6f, minPhase = 1 },
                new AttackPattern { name = "Shiko doble", steps = new[] { shikoD, shikoI }, weight = 1f, maxRange = 6.5f, cooldown = 9f, minPhase = 1 },
                new AttackPattern { name = "Doble tachiai", steps = new[] { tachiai, tachiai }, weight = 1.1f, minRange = 6f, maxRange = 10.5f, cooldown = 8f, minPhase = 1 },
                new AttackPattern { name = "Shio", steps = new[] { salt }, weight = 0.5f, maxRange = 20f, cooldown = 18f, minPhase = 1 },
            };
            return c;
        }

        // ------------------------------------------------------------------ movimientos de las variantes de zona
        // EnemyVariants los suma según la región donde aparece el enemigo. Todo dentro de la gramática del aviso:
        // dorado = parry, rojo = dash; cada zona agrega una mezcla propia, no golpes más rápidos.

        /// <summary>Ninja de la montaña: más pesado y lento; dos cortes y un tajo de arriba IMPARABLE (rompeguardia).</summary>
        public static void NinjaMountainMoves(EnemyConfig c)
        {
            c.ScaleSteps(1.1f, 0.92f);
            var a1 = Hit("Attack1", 14, 0.583f, 0.75f, telegraph: 0.15f, speed: 0.92f, apex: NinjaApex1);
            var a2 = Hit("Attack2", 14, 0.455f, 0.636f, speed: 0.92f, apex: NinjaApex2);
            // el tajo de arriba con todo el peso: 0.95 s de carga (VariantMotion lo echa atrás antes de soltar)
            var breaker = Hit("Attack3", 20, 0.5f, 0.618f, range: 2.6f, arc: 120, kind: AttackKind.Unblockable, lunge: 1.3f, kb: 2.2f, apex: NinjaApex3);
            breaker.windup = 0.95f; breaker.name = "Rompeguardia";
            Weight(c, "Combo de 3", 1f);
            Add(c, new AttackPattern { name = "Avalancha", steps = new[] { a1, a2, breaker }, weight = 1.6f, maxRange = 2.8f, cooldown = 5f },
                   new AttackPattern { name = "Rompeguardia", steps = new[] { breaker }, weight = 0.6f, maxRange = 2.8f, cooldown = 7f });
        }

        /// <summary>Ninja del lago: fluido; un corte y un remolino de 360° (dorado) y el arpón que llega de lejos.</summary>
        public static void NinjaLakeMoves(EnemyConfig c)
        {
            var a1 = Hit("Attack1", 12, 0.583f, 0.75f, telegraph: 0.1f, apex: NinjaApex1);
            var whirl = Hit("Attack2", 14, 0.455f, 0.636f, range: 2.7f, arc: 360, kind: AttackKind.Heavy, lunge: 1.1f, telegraph: 0.1f, kb: 1.4f, apex: NinjaApex2);
            whirl.name = "Remolino";
            // el arpón es la estocada voladora (clip Thrust) con menos recorrido
            var harpoon = Hit("Thrust", 16, 0.525f, 0.625f, range: 3.2f, kind: AttackKind.Heavy, lunge: 2.4f, kb: 1.2f, apex: NinjaApexThrust);
            harpoon.windup = 0.75f; harpoon.name = "Arpón";
            Remove(c, "Estocada");
            // alcance real: 3.2 + 2.4 de embestida + el radio de Kaito = 5.95 m; arranca a 5.5 como mucho (si no, el
            // anillo se cerraba sobre un golpe que no llegaba y enseñaba un parry falso)
            Add(c, new AttackPattern { name = "Marea", steps = new[] { a1, whirl }, weight = 1.6f, maxRange = 2.8f },
                   new AttackPattern { name = "Arpón", steps = new[] { harpoon }, weight = 1.2f, minRange = 2.8f, maxRange = 5.5f, cooldown = 4f });
        }

        /// <summary>Ninja del bambú: acrobático; entra de un salto desde 4-6.5 m y después de un combo se repliega.</summary>
        public static void NinjaBambooMoves(EnemyConfig c)
        {
            var a1 = Hit("Attack1", 12, 0.583f, 0.75f, telegraph: 0.12f, apex: NinjaApex1);
            var a2 = Hit("Attack2", 12, 0.455f, 0.636f, apex: NinjaApex2);
            // el salto: el aviso dura lo que tarda en cerrar la distancia (VariantMotion lo levanta en el aire)
            var leap = Hit("Attack3", 16, 0.5f, 0.618f, range: 2.4f, kind: AttackKind.Heavy, lunge: 4.4f, kb: 1.4f, apex: NinjaApex3);
            leap.windup = 0.8f; leap.name = "Salto";
            // repliegue: salto atrás de 3 m sin daño (queda a tiro de otro salto)
            var hop = Hit("Spotted", 0, 0.15f, 0.6f, lunge: 0f, telegraph: 0.12f);
            hop.special = "hop_back"; hop.specialParam = 3f; hop.name = "Repliegue";
            Remove(c, "Estocada");
            // alcance real del salto: 2.4 + 4.4 + 0.35 = 7.15 m. El patrón se elige el primer frame que entra en rango
            // (corriendo hacia Kaito arranca casi siempre en el borde): a 6.6 queda medio metro de margen
            Add(c, new AttackPattern { name = "Salto", steps = new[] { leap }, weight = 1.5f, minRange = 3.8f, maxRange = 6.6f, cooldown = 3.5f },
                   new AttackPattern { name = "Golpe y repliegue", steps = new[] { a1, a2, hop }, weight = 1.6f, maxRange = 2.8f });
        }

        /// <summary>Sumo de la montaña: más lento y pesado; el pisotón es un shiko IMPARABLE con un disco de 4.6 m.</summary>
        public static void SumoMountainMoves(EnemyConfig c)
        {
            c.ScaleSteps(1.1f, 0.9f);
            var stomp = Hit("Attack3", 26, 0.643f, 0.738f, range: 3.4f, arc: 360, kind: AttackKind.Unblockable, lunge: 0.2f, telegraph: 0.15f, kb: 2.6f, apex: SumoApex3);
            stomp.special = "slam"; stomp.specialParam = 4.6f; stomp.tracking = false; stomp.name = "Shiko D";
            Remove(c, "Pisotón");
            Add(c, new AttackPattern { name = "Shiko de nieve", steps = new[] { stomp }, weight = 1.2f, maxRange = 4f, cooldown = 5f });
        }

        /// <summary>Sumo del lago: una bofetada y el empujón a dos manos que te saca lejos (dorado, con salpicón).</summary>
        public static void SumoLakeMoves(EnemyConfig c)
        {
            var slap = Hit("Attack1", 18, 0.667f, 0.815f, range: 2.8f, arc: 120, kind: AttackKind.Heavy, lunge: 0.6f, kb: 1.6f, apex: SumoApex1);
            var morote = Hit("Attack2", 20, 0.593f, 0.741f, range: 3.0f, arc: 120, kind: AttackKind.Heavy, lunge: 1.6f, kb: 3.8f, apex: SumoApex2);
            morote.name = "Morote";
            Weight(c, "Bofetadas", 1.2f);
            Add(c, new AttackPattern { name = "Oleaje", steps = new[] { slap, morote }, weight = 1.6f, maxRange = 3.4f });
        }

        /// <summary>Sumo del bambú: se corre de costado de un salto (la finta) y embiste desde ahí.</summary>
        public static void SumoBambooMoves(EnemyConfig c)
        {
            var feint = Hit("Spotted", 0, 0.15f, 0.7f, lunge: 0f, telegraph: 0.1f);
            feint.special = "hop_side"; feint.specialParam = 2.6f; feint.name = "Finta";
            var charge = Hit("Special", 30, 0.3f, 0.7f, range: 2.4f, arc: 90, kind: AttackKind.Unblockable, lunge: 0f, kb: 3f, apex: SumoApexSpecial);
            charge.special = "charge"; charge.specialParam = 13f; charge.tracking = true;
            Add(c, new AttackPattern { name = "Finta y embestida", steps = new[] { feint, charge }, weight = 1.5f, minRange = 3.5f, maxRange = 10f, cooldown = 5f });
        }

        static void Add(EnemyConfig c, params AttackPattern[] add)
        {
            var list = new System.Collections.Generic.List<AttackPattern>(c.patterns ?? new AttackPattern[0]);
            list.AddRange(add);
            c.patterns = list.ToArray();
        }

        static void Remove(EnemyConfig c, string pattern)
        {
            if (c.patterns == null) return;
            c.patterns = System.Array.FindAll(c.patterns, p => p != null && p.name != pattern);
        }

        static void Weight(EnemyConfig c, string pattern, float w)
        {
            if (c.patterns != null) foreach (var p in c.patterns) if (p != null && p.name == pattern) p.weight = w;
        }

        /// <summary>
        /// Kokuyō, Señor del Clan Kurokage (jefe final). El arquetipo sigue llamándose "kage" (banderas del guardado, la
        /// puerta y el final); sus golpes, tiempos y actos viven en Enemies/Bosses (KokuyoMoves, KokuyoBoss). Los clones
        /// de sombra del Kage viejo se retiraron: su sombra arrancada (KageShadow) los reemplaza.
        /// </summary>
        public static EnemyConfig Kage() => KokuyoMoves.Kokuyo();
    }
}
