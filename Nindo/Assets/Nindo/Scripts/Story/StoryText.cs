using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Todos los textos del juego en un solo lugar (zonas, santuarios, diálogos, objetivos).
    /// Para cambiar la historia o traducir, se edita este archivo.
    /// </summary>
    public static class StoryText
    {
        public const string Kaito = "Kaito";
        public const string Abuelo = "Abuelo";
        public const string Ninja = "Ninja Kurokage";
        public const string Kage = "Kage";

        public static string CheckpointName(string id)
        {
            switch (id)
            {
                case "cp_home": return "Santuario del Hogar";
                case "cp_fields": return "Santuario de Inaba";
                case "cp_forest": return "Santuario del Bosque";
                case "cp_wall": return "Santuario de la Muralla";
                case "cp_garden": return "Santuario del Jardín";
                case "cp_dojo_gate": return "Santuario del Dojo";
                case "cp_mountain": return "Santuario de Kodoyama";
                case "cp_mountain_top": return "Santuario de la Cumbre";
                case "cp_lake": return "Santuario del Lago";
                case "cp_lake_docks": return "Santuario de los Muelles";
                case "cp_bamboo": return "Santuario del Bambú";
                case "cp_dojo": return "Santuario del Patio";
                default: return "Santuario";
            }
        }

        public static void ConfigureZone(Zone z)
        {
            switch (z.id)
            {
                case "hogar":
                    z.title = "Hogar de Kaito"; z.subtitle = "La colina del abuelo";
                    z.music = "explore_home"; z.ambience = "night";
                    z.fogColor = new Color(0.07f, 0.1f, 0.17f); z.fogDensity = 0.010f; z.ambientSky = new Color(0.24f, 0.3f, 0.45f);
                    break;
                case "campos":
                    z.title = "Campos de Inaba"; z.subtitle = "Aldea de granjeros";
                    z.music = "explore_home"; z.ambience = "night";
                    z.fogColor = new Color(0.08f, 0.11f, 0.17f); z.fogDensity = 0.010f; z.ambientSky = new Color(0.24f, 0.3f, 0.44f);
                    break;
                case "bosque":
                    z.title = "Linde del Bosque"; z.subtitle = "Donde la luna no llega";
                    z.music = "explore_forest"; z.ambience = "forest";
                    z.fogColor = new Color(0.06f, 0.09f, 0.11f); z.fogDensity = 0.012f; z.ambientSky = new Color(0.2f, 0.27f, 0.34f);
                    break;
                case "muralla":
                    z.title = "La Muralla Kurokage"; z.subtitle = "Territorio del clan";
                    z.music = "explore_forest"; z.ambience = "forest";
                    z.fogColor = new Color(0.07f, 0.09f, 0.14f); z.fogDensity = 0.011f; z.ambientSky = new Color(0.22f, 0.27f, 0.38f);
                    break;
                case "jardin":
                    z.title = "Jardín del Clan"; z.subtitle = "La aldea de las luciérnagas";
                    z.music = "explore_garden"; z.ambience = "garden";
                    z.fogColor = new Color(0.07f, 0.09f, 0.16f); z.fogDensity = 0.008f; z.ambientSky = new Color(0.26f, 0.3f, 0.48f);
                    break;
                case "dojo":
                    z.title = "Dojo Kurokage"; z.subtitle = "El final del camino";
                    z.music = "explore_dojo"; z.ambience = "wind";
                    z.fogColor = new Color(0.1f, 0.06f, 0.1f); z.fogDensity = 0.010f; z.ambientSky = new Color(0.3f, 0.22f, 0.36f);
                    break;
                case "montana":
                    z.title = "Montaña Kodoyama"; z.subtitle = "Rocas, nieve y silencio";
                    z.music = "explore_mountain"; z.ambience = "wind"; z.snow = true;
                    z.fogColor = new Color(0.16f, 0.19f, 0.26f); z.fogDensity = 0.012f; z.ambientSky = new Color(0.32f, 0.38f, 0.52f);
                    break;
                case "lago":
                    z.title = "Aldea del Lago Kohan"; z.subtitle = "Pescadores bajo la luna";
                    z.music = "explore_lake"; z.ambience = "water";
                    z.fogColor = new Color(0.06f, 0.12f, 0.16f); z.fogDensity = 0.012f; z.ambientSky = new Color(0.22f, 0.32f, 0.45f);
                    break;
                case "lago_cascada":
                    // arena de Mizuchi: cámara más baja y algo más lejos, si no la cascada queda arriba del cuadro
                    z.title = "Cascada Kohan"; z.subtitle = "Donde los koi se vuelven dragones";
                    z.music = "explore_lake"; z.ambience = "water";
                    z.fogColor = new Color(0.06f, 0.12f, 0.16f); z.fogDensity = 0.012f; z.ambientSky = new Color(0.22f, 0.32f, 0.45f);
                    z.cameraPitchOffset = -4f; z.cameraDistanceOffset = 1f;
                    break;
                case "bambu":
                    z.title = "Bosque de Bambú"; z.subtitle = "El susurro del viento";
                    z.music = "explore_forest"; z.ambience = "bamboo";
                    z.fogColor = new Color(0.08f, 0.13f, 0.11f); z.fogDensity = 0.011f; z.ambientSky = new Color(0.23f, 0.33f, 0.31f);
                    break;
                default:
                    z.title = z.id; break;
            }
        }

        static DialogueLine L(string s, string t) => new DialogueLine(s, t);

        public static List<DialogueLine> Dialogue(string id)
        {
            switch (id)
            {
                case "intro_wake":
                    return new List<DialogueLine> {
                        L(Kaito, "Ugh... mi cabeza... ¿Qué pasó? Había un ruido en los cultivos y..."),
                        L(Abuelo, "¡KAITO! ¡Desatá la cinta de la guadaña! ¡Rápido!"),
                    };
                case "intro_bandana":
                    return new List<DialogueLine> {
                        L(Kaito, "La cinta... ¡se me ató sola! Y la guadaña... ¡es una katana!"),
                        L(Kaito, "Siento... todo lo que sabe el abuelo. Cada movimiento."),
                        L(Ninja, "¿La bandana del viejo? ...Llevátelo. Yo me encargo del mocoso."),
                    };
                case "intro_after_fight":
                    return new List<DialogueLine> {
                        L(Kaito, "Se llevaron al abuelo hacia el norte. Voy a seguir su rastro."),
                        L(Kaito, "Abuelo... aguantá. Ya voy."),
                    };
                case "fields":
                    return new List<DialogueLine> {
                        L(Kaito, "Huellas en el barro... y tiraron sus cosas por todos lados. Van hacia el bosque."),
                    };
                case "forest_reveal":
                    return new List<DialogueLine> {
                        L(Abuelo, "¡No te rindas, Kaito! ¡Recordá: el camino ninja no se recorre solo!"),
                        L(Kaito, "¡ABUELO! ...Lo arrastran hacia la muralla del clan."),
                    };
                case "wall_guards":
                    return new List<DialogueLine> {
                        L(Ninja, "¡Alto ahí! Nadie cruza la muralla Kurokage."),
                        L(Kaito, "Entonces voy a tener que abrirla yo."),
                    };
                case "wall_open":
                    return new List<DialogueLine> {
                        L(Kaito, "El portón está abierto. Más allá está el jardín del clan."),
                    };
                case "garden":
                    return new List<DialogueLine> {
                        L(Kaito, "Tantas luces... tantos guardias. Tengo que tener cuidado y pelear con la cabeza."),
                    };
                case "sumo_intro":
                    return new List<DialogueLine> {
                        L("Luchador de Sumo", "¡JA! ¿Este es el nieto del viejo? ¡Te voy a aplastar como a un grano de arroz!"),
                    };
                case "abilities":
                    return new List<DialogueLine> {
                        L(Kaito, "La bandana brilla... el espíritu del abuelo me habla."),
                        L("Espíritu de la Bandana", "Usá mi fuerza cuando el espíritu esté lleno. Corte del Viento [1] y Torbellino de Hojas [2]."),
                    };
                case "dojo_gate":
                    return new List<DialogueLine> {
                        L(Kaito, "La puerta del dojo... tiene tres huecos. Sellos."),
                        L(Kaito, "Uno en la Montaña Kodoyama, al oeste. Otro en la Aldea del Lago, al este. Y el último en el Bosque de Bambú, al noreste."),
                        L(Kaito, "Los guardianes de cada sello me esperan. Abuelo, ya falta poco."),
                    };
                case "dojo_gate_incomplete":
                    return new List<DialogueLine> {
                        L(Kaito, "Todavía faltan sellos. Montaña al oeste, lago al este, bambú al noreste."),
                    };
                case "dojo_gate_open":
                    return new List<DialogueLine> {
                        L(Kaito, "Los tres sellos... ¡la puerta se abre!"),
                    };
                case "goro_intro":
                    return new List<DialogueLine> {
                        L("Gorō", "Hmmm... Un niño con una espada de juguete. Mi martillo ha roto montañas más grandes que vos."),
                    };
                case "mizuchi_intro":
                    return new List<DialogueLine> {
                        L("Mizuchi", "El lago devora a los que se atreven a cruzarlo. Ahogate en la marea, pequeño."),
                    };
                case "ozeki_intro":
                    return new List<DialogueLine> {
                        L("Ōzeki", "¡El bambú se dobla pero no se quiebra! ¡Pero vos sí te vas a quebrar!"),
                    };
                case "kage_intro":
                    return new List<DialogueLine> {
                        L(Kage, "Así que el viejo te dio su bandana. Yo fui su alumno, ¿sabías? Hasta que me dejó solo."),
                        L(Kage, "Soy la sombra de lo que vos vas a ser. Veamos si sos digno de ese camino."),
                        L(Kaito, "No estoy solo. Nunca lo estuve."),
                    };
                case "seal_mountain":
                    return new List<DialogueLine> { L(Kaito, "El Sello de la Montaña. Un portal apareció: me lleva de vuelta al dojo.") };
                case "seal_lake":
                    return new List<DialogueLine> { L(Kaito, "El Sello del Agua. Ya casi.") };
                case "seal_bamboo":
                    return new List<DialogueLine> { L(Kaito, "El Sello del Bambú.") };
                case "ending":
                    return new List<DialogueLine> {
                        L(Abuelo, "Kaito... viniste. Sabía que la bandana te elegiría."),
                        L(Kaito, "Abuelo... ¿estás bien? ¿Quién era él?"),
                        L(Abuelo, "Alguien que eligió caminar solo. El verdadero poder nace del lazo que nos une a los nuestros."),
                        L(Abuelo, "Vamos a casa, nieto. Ese es tu nindō: el camino ninja."),
                    };
                case "grandpa_home":
                    return new List<DialogueLine> { L(Abuelo, "...") };
                default:
                    return new List<DialogueLine> { L("", id) };
            }
        }

        public static string Objective(SaveData s)
        {
            if (!s.HasFlag(Flags.KatanaObtained)) return "Desatá la cinta de la guadaña";
            if (!s.HasFlag(Flags.Encounter("intro"))) return "Defendete";
            if (!s.HasFlag(Flags.WallGateOpen)) return "Seguí el rastro de los secuestradores hacia el norte";
            if (!s.HasFlag(Flags.DojoGateSeen)) return "Atravesá el Jardín del Clan hasta el dojo";
            if (s.SealCount < 3)
            {
                var missing = new List<string>();
                if (!s.HasSeal(SealId.Montana)) missing.Add("Montaña (oeste)");
                if (!s.HasSeal(SealId.Lago)) missing.Add("Lago (este)");
                if (!s.HasSeal(SealId.Bambu)) missing.Add("Bambú (noreste)");
                return $"Conseguí los sellos ({s.SealCount}/3): " + string.Join(", ", missing);
            }
            if (!s.HasFlag(Flags.DojoOpen)) return "Volvé a la puerta del dojo con los tres sellos";
            if (!s.HasFlag(Flags.FinalBossDone)) return "Rescatá al abuelo";
            return "";
        }
    }
}
