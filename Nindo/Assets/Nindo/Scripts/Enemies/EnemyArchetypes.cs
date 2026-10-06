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

        /// <summary>Mizuchi, la Marea (jefe del lago): ninja veloz que lanza olas y llama refuerzos.</summary>
        public static EnemyConfig Mizuchi()
        {
            var c = Ninja();
            c.id = "mizuchi"; c.displayName = "Mizuchi"; c.maxHealth = 420; c.scale = 1.3f; c.runSpeed = 6.2f;
            c.maxImbalance = 5; c.exhaustedTime = 3f; c.guardTime = 1.6f; c.poiseHits = 2; c.detectRadius = 30; c.loseRadius = 80;
            c.finisherHealth = 0.12f; c.tint = new Color(0.2f, 0.65f, 0.8f); c.tintStrength = 0.5f; c.hyperArmor = false;
            var a1 = Hit("Attack1", 16, 0.6f, 0.78f, telegraph: 0.08f, speed: 1.15f, apex: NinjaApex1);
            var a2 = Hit("Attack2", 16, 0.42f, 0.62f, speed: 1.15f, apex: NinjaApex2);
            var a3 = Hit("Attack3", 20, 0.5f, 0.7f, kind: AttackKind.Heavy, lunge: 1.6f, speed: 1.1f, kb: 1.5f, apex: NinjaApex3);
            var wave = Hit("Attack3", 18, 0.5f, 0.6f, kind: AttackKind.Light, lunge: 0f, telegraph: 0.25f, apex: NinjaApex3);
            wave.special = "wave"; wave.specialParam = 1;
            var wave3 = wave.Clone(); wave3.specialParam = 3;
            var summon = Hit("Spotted", 0, 0.5f, 0.55f, lunge: 0f); summon.special = "summon"; summon.specialParam = 2;
            var tp = Hit("Attack2", 0, 0.3f, 0.35f, lunge: 0f); tp.special = "teleport"; tp.specialParam = 2.4f;
            c.patterns = new[]
            {
                new AttackPattern { name = "Marea", steps = new[] { a1, a2, a3 }, weight = 2f, maxRange = 3f },
                new AttackPattern { name = "Ola", steps = new[] { wave }, weight = 1.3f, minRange = 4f, maxRange = 16f, cooldown = 3f },
                new AttackPattern { name = "Tres olas", steps = new[] { wave3, wave }, weight = 1.2f, minRange = 3f, maxRange = 16f, cooldown = 6f, minPhase = 1 },
                new AttackPattern { name = "Corriente", steps = new[] { tp, a1, a2 }, weight = 1f, maxRange = 12f, cooldown = 7f, minPhase = 1 },
                new AttackPattern { name = "Llamado", steps = new[] { summon }, weight = 0.8f, maxRange = 20f, cooldown = 25f, minPhase = 1 },
            };
            return c;
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
            c.id = "ozeki"; c.displayName = "Ōzeki"; c.maxHealth = 560; c.scale = 1.35f; c.maxImbalance = 4;
            c.detectRadius = 30; c.loseRadius = 80; c.finisherHealth = 0.12f; c.exhaustedTime = 4f; c.guardTime = 0.8f;
            c.runSpeed = 3.8f; c.walkSpeed = 1.8f; c.turnSpeed = 6.5f; c.preferredDistance = 4.4f;
            c.attackCooldown = new Vector2(0.6f, 1.3f);
            // sin tinte: lo viste su kit (tsuna, delantal violeta, abanico dorado)
            c.tint = Color.white; c.tintStrength = 0f;
            var hD = Hit("Attack1", 16, 0.7f, 0.9f, range: 3.0f, arc: 120, kind: AttackKind.Heavy, lunge: 0.9f, telegraph: 0.05f, kb: 2f, apex: SumoApex1);
            hD.name = "Harite D";
            var hI = Hit("Attack2", 16, 0.6f, 0.82f, range: 3.0f, arc: 120, kind: AttackKind.Heavy, lunge: 0.9f, kb: 2f, apex: SumoApex2);
            hI.name = "Harite I";
            // la última del tsuppari furioso se demora un tercio de segundo: el que aprieta por ritmo se adelanta
            var hLate = hD.Clone(); hLate.telegraph = 0.32f;
            // agarre: imparable de cerca (solo dash, o salir de adelante cuando abre los brazos)
            var grab = Hit("Attack2", 26, 0.6f, 0.82f, range: 3.0f, arc: 100, kind: AttackKind.Unblockable, lunge: 1.5f, telegraph: 0.1f, kb: 3.5f, apex: SumoApex2);
            grab.special = "grab"; grab.name = "Agarre";
            // shiko: la pierna sube ~1.1 s (el clip del pisotón) y la onda se abre a 7 m/s hasta 8 m
            var shikoD = Hit("Attack3", 22, 0.8f, 0.92f, range: 3.0f, arc: 360, kind: AttackKind.Unblockable, lunge: 0f, telegraph: 0.05f, kb: 2.6f, apex: SumoApex3);
            shikoD.special = "shiko"; shikoD.specialParam = 8f; shikoD.tracking = false; shikoD.name = "Shiko D";
            var shikoI = shikoD.Clone(); shikoI.name = "Shiko I";
            // tachiai: 0.5 s agachándose y 0.45 s quieto con los puños en el piso; después 13 m/s por un carril fijo.
            // Desde 6-10.5 m: más cerca no hay tiempo de salir corriendo del carril; más lejos arranca fuera de cuadro
            var tachiai = Hit("Special", 28, 0.35f, 0.85f, range: 2.6f, arc: 90, kind: AttackKind.Unblockable, lunge: 0f, telegraph: 0.2f, kb: 4f, apex: SumoApexSpecial);
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
            var a1 = Hit("Attack1", 14, 0.6f, 0.78f, telegraph: 0.15f, speed: 0.92f, apex: NinjaApex1);
            var a2 = Hit("Attack2", 14, 0.42f, 0.62f, speed: 0.92f, apex: NinjaApex2);
            // el tajo de arriba con todo el peso: 0.95 s de carga (VariantMotion lo echa atrás antes de soltar)
            var breaker = Hit("Attack3", 20, 0.5f, 0.7f, range: 2.6f, arc: 120, kind: AttackKind.Unblockable, lunge: 1.3f, kb: 2.2f, apex: NinjaApex3);
            breaker.windup = 0.95f; breaker.name = "Rompeguardia";
            Weight(c, "Combo de 3", 1f);
            Add(c, new AttackPattern { name = "Avalancha", steps = new[] { a1, a2, breaker }, weight = 1.6f, maxRange = 2.8f, cooldown = 5f },
                   new AttackPattern { name = "Rompeguardia", steps = new[] { breaker }, weight = 0.6f, maxRange = 2.8f, cooldown = 7f });
        }

        /// <summary>Ninja del lago: fluido; un corte y un remolino de 360° (dorado) y el arpón que llega de lejos.</summary>
        public static void NinjaLakeMoves(EnemyConfig c)
        {
            var a1 = Hit("Attack1", 12, 0.6f, 0.78f, telegraph: 0.1f, apex: NinjaApex1);
            var whirl = Hit("Attack2", 14, 0.42f, 0.62f, range: 2.7f, arc: 360, kind: AttackKind.Heavy, lunge: 1.1f, telegraph: 0.1f, kb: 1.4f, apex: NinjaApex2);
            whirl.name = "Remolino";
            var harpoon = Hit("Attack3", 16, 0.5f, 0.7f, range: 3.2f, kind: AttackKind.Heavy, lunge: 2.4f, kb: 1.2f, apex: NinjaApex3);
            harpoon.windup = 0.75f; harpoon.name = "Arpón";
            Remove(c, "Estocada");
            Add(c, new AttackPattern { name = "Marea", steps = new[] { a1, whirl }, weight = 1.6f, maxRange = 2.8f },
                   new AttackPattern { name = "Arpón", steps = new[] { harpoon }, weight = 1.2f, minRange = 2.8f, maxRange = 6f, cooldown = 4f });
        }

        /// <summary>Ninja del bambú: acrobático; entra de un salto desde 4-7 m y después de un combo se repliega.</summary>
        public static void NinjaBambooMoves(EnemyConfig c)
        {
            var a1 = Hit("Attack1", 12, 0.6f, 0.78f, telegraph: 0.12f, apex: NinjaApex1);
            var a2 = Hit("Attack2", 12, 0.42f, 0.62f, apex: NinjaApex2);
            // el salto: el aviso dura lo que tarda en cerrar la distancia (VariantMotion lo levanta en el aire)
            var leap = Hit("Attack3", 16, 0.5f, 0.7f, range: 2.4f, kind: AttackKind.Heavy, lunge: 4.4f, kb: 1.4f, apex: NinjaApex3);
            leap.windup = 0.8f; leap.name = "Salto";
            // repliegue: salto atrás de 3 m sin daño (queda a tiro de otro salto)
            var hop = Hit("Spotted", 0, 0.15f, 0.6f, lunge: 0f, telegraph: 0.12f);
            hop.special = "hop_back"; hop.specialParam = 3f; hop.name = "Repliegue";
            Remove(c, "Estocada");
            Add(c, new AttackPattern { name = "Salto", steps = new[] { leap }, weight = 1.5f, minRange = 3.8f, maxRange = 7.5f, cooldown = 3.5f },
                   new AttackPattern { name = "Golpe y repliegue", steps = new[] { a1, a2, hop }, weight = 1.6f, maxRange = 2.8f });
        }

        /// <summary>Sumo de la montaña: más lento y pesado; el pisotón es un shiko IMPARABLE con un disco de 4.6 m.</summary>
        public static void SumoMountainMoves(EnemyConfig c)
        {
            c.ScaleSteps(1.1f, 0.9f);
            var stomp = Hit("Attack3", 26, 0.8f, 0.92f, range: 3.4f, arc: 360, kind: AttackKind.Unblockable, lunge: 0.2f, telegraph: 0.15f, kb: 2.6f, apex: SumoApex3);
            stomp.special = "slam"; stomp.specialParam = 4.6f; stomp.tracking = false; stomp.name = "Shiko D";
            Remove(c, "Pisotón");
            Add(c, new AttackPattern { name = "Shiko de nieve", steps = new[] { stomp }, weight = 1.2f, maxRange = 4f, cooldown = 5f });
        }

        /// <summary>Sumo del lago: una bofetada y el empujón a dos manos que te saca lejos (dorado, con salpicón).</summary>
        public static void SumoLakeMoves(EnemyConfig c)
        {
            var slap = Hit("Attack1", 18, 0.7f, 0.9f, range: 2.8f, arc: 120, kind: AttackKind.Heavy, lunge: 0.6f, kb: 1.6f, apex: SumoApex1);
            var morote = Hit("Attack2", 20, 0.6f, 0.82f, range: 3.0f, arc: 120, kind: AttackKind.Heavy, lunge: 1.6f, kb: 3.8f, apex: SumoApex2);
            morote.name = "Morote";
            Weight(c, "Bofetadas", 1.2f);
            Add(c, new AttackPattern { name = "Oleaje", steps = new[] { slap, morote }, weight = 1.6f, maxRange = 3.4f });
        }

        /// <summary>Sumo del bambú: se corre de costado de un salto (la finta) y embiste desde ahí.</summary>
        public static void SumoBambooMoves(EnemyConfig c)
        {
            var feint = Hit("Spotted", 0, 0.15f, 0.7f, lunge: 0f, telegraph: 0.1f);
            feint.special = "hop_side"; feint.specialParam = 2.6f; feint.name = "Finta";
            var charge = Hit("Special", 30, 0.35f, 0.85f, range: 2.4f, arc: 90, kind: AttackKind.Unblockable, lunge: 0f, kb: 3f, apex: SumoApexSpecial);
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
