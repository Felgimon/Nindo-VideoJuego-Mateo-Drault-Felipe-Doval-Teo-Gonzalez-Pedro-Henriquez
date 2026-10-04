// Agua low-poly animada de Nindō (URP).
//  * Olas: suma de 3 senos direccionales en el vertex shader (misma fórmula que la vista previa de
//    Tools/Blender/world/build_world.py -> wave_height). La amplitud por vértice viene en color.r.
//  * Facetas: la normal se reconstruye por triángulo con ddx/ddy, así cada cara refleja la luna
//    por separado y el agua "titila" cuando se mueve. La pendiente real de las olas es chica (< 8°),
//    así que para sombrear se exagera (_FacetBoost); la geometría (y FloatingBob) no cambia.
//  * Crestas: cada cara se aclara (y tira a turquesa) en la cresta y se oscurece en el valle, según
//    la ola en su vértice: las olas se leen como bandas que avanzan aunque midan centímetros.
//  * Facetas finas: una grilla de triángulos más chica que la malla (en espacio mundo) inclina la
//    normal de cada triángulo con una fase propia y un frente que avanza: el agua se ve "picada" en
//    facetas low-poly que titilan y corren. Se apaga sola de lejos (cuando ocupan pocos píxeles).
//  * Espuma: color.g = cercanía a la orilla. Se evalúa por triángulo (nointerpolation) con un
//    umbral que late con el tiempo: los triángulos de la orilla se encienden y apagan como olas.
//  * Profundidad: color.b -> color (bajo turquesa, hondo azul noche) y transparencia.
//  * Destellos: algunas facetas brillan un instante (reflejo de la luna).
// Si el shader no compila, WorldBuilder deja el material Lit de siempre.
Shader "Nindo/Water Lowpoly"
{
    Properties
    {
        _ShallowColor ("Color bajo", Color) = (0.13, 0.42, 0.47, 1)
        _DeepColor ("Color hondo", Color) = (0.02, 0.08, 0.17, 1)
        _FoamColor ("Espuma", Color) = (0.78, 0.9, 0.95, 1)
        _SkyColor ("Reflejo del cielo", Color) = (0.2, 0.3, 0.48, 1)
        _SparkleColor ("Destellos", Color) = (1.0, 0.97, 0.85, 1)
        _CrestColor ("Color de las crestas", Color) = (0.36, 0.66, 0.68, 1)
        _AlphaShallow ("Opacidad en lo bajo", Range(0, 1)) = 0.55
        _AlphaDeep ("Opacidad en lo hondo", Range(0, 1)) = 0.92
        _WaveHeight ("Altura de las olas", Range(0, 1)) = 0.26
        _WaveSpeed ("Velocidad de las olas", Range(0, 4)) = 1.0
        _Gloss ("Brillo especular", Range(4, 256)) = 128
        _FacetBoost ("Exageración de facetas", Range(1, 12)) = 4.5
        _SpecStrength ("Intensidad especular", Range(0, 4)) = 1.4
        _FoamThreshold ("Umbral de espuma", Range(0, 1)) = 0.64
        _SparkleAmount ("Cantidad de destellos", Range(0, 1)) = 0.06
        _CrestContrast ("Contraste crestas/valles", Range(0, 1)) = 0.35
        _RippleScale ("Tamaño de las facetas finas (m)", Range(0.25, 4)) = 0.9
        _RippleStrength ("Inclinación de las facetas finas", Range(0, 1)) = 0.3
        _RippleSpeed ("Velocidad de las facetas finas", Range(0, 4)) = 1.0
    }

    SubShader
    {
        Tags { "RenderType" = "Transparent" "Queue" = "Transparent-10" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }
        LOD 200

        Pass
        {
            Name "ForwardWater"
            Tags { "LightMode" = "UniversalForward" }
            Blend SrcAlpha OneMinusSrcAlpha
            ZWrite Off
            Cull Back

            HLSLPROGRAM
            #pragma target 3.5
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE
            #pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
            #pragma multi_compile _ _CLUSTER_LIGHT_LOOP
            #pragma multi_compile_fragment _ _SHADOWS_SOFT
            #pragma multi_compile_fog

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _ShallowColor;
                half4 _DeepColor;
                half4 _FoamColor;
                half4 _SkyColor;
                half4 _SparkleColor;
                half4 _CrestColor;
                half _AlphaShallow;
                half _AlphaDeep;
                float _WaveHeight;
                float _WaveSpeed;
                half _Gloss;
                half _FacetBoost;
                half _SpecStrength;
                half _FoamThreshold;
                half _SparkleAmount;
                half _CrestContrast;
                float _RippleScale;
                half _RippleStrength;
                float _RippleSpeed;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                float4 color : COLOR;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                // valores por triángulo (del vértice "provocador"): look facetado
                nointerpolation float4 facet : TEXCOORD1;   // xy = posición xz del vértice, z = orilla, w = profundidad
                float depth : TEXCOORD2;
                float fogFactor : TEXCOORD3;
                nointerpolation float2 wave : TEXCOORD4;   // x = ola en el vértice (-1 valle .. 1 cresta), y = amplitud (color.r)
                #if defined(_ADDITIONAL_LIGHTS_VERTEX)
                half3 vertexLight : TEXCOORD5;   // faroles por vértice (calidad Baja / Muy baja)
                #endif
            };

            // misma fórmula que wave_height() en build_world.py y FloatingBob.Wave, sin escalar (-1..1):
            // la altura real es WaveSum * _WaveHeight * amplitud
            float WaveSum(float2 xz, float t)
            {
                return 0.55 * sin(dot(float2(0.958, 0.287), xz) * 0.35 + t * 1.1)
                     + 0.30 * sin(dot(float2(-0.371, 0.928), xz) * 0.55 + t * 1.5)
                     + 0.15 * sin(dot(float2(0.659, -0.753), xz) * 0.90 + t * 2.1);
            }

            float Hash(float2 p)
            {
                return frac(sin(dot(p, float2(12.9898, 78.233))) * 43758.5453);
            }

            // Facetas finas: grilla de triángulos equiláteros en espacio mundo (más chica que la malla de
            // 2 m y girada respecto de ella). Devuelve la inclinación (xz) del triángulo donde cae 'xz':
            // fase propia (hash) + un frente que avanza, así titilan y "corren" como agua picada.
            // id = valor fijo por triángulo (0..1); fade = 0 cuando los triángulos ocupan pocos píxeles.
            float2 RippleTilt(float2 xz, float t, out float id, out float fade)
            {
                float2 p = float2(0.8 * xz.x - 0.6 * xz.y, 0.6 * xz.x + 0.8 * xz.y) / _RippleScale;
                float2 s = p + (p.x + p.y) * 0.3660254;   // sesgo de simplex: cada celda = 2 triángulos equiláteros
                float2 cell = floor(s);
                float2 f = s - cell;
                float lower = step(f.y, f.x);              // qué triángulo de la celda
                id = Hash(cell + lower * float2(0.5, 0.25));
                float r2 = Hash(cell + lower * float2(0.5, 0.25) + 17.31);
                float2 c = cell + lerp(float2(0.3333, 0.6667), float2(0.6667, 0.3333), lower);   // centro (grilla sesgada)
                float a = id * 6.2832 + dot(c, float2(0.62, 0.38)) * 1.3 - t * 1.6;
                float2 tilt = float2(sin(a + t * (0.7 + r2)), cos(a * 0.8 + r2 * 6.2832 - t * (0.5 + id)));
                // celdas por píxel: de lejos se apaga en vez de parpadear (aliasing)
                float px = max(fwidth(s.x), fwidth(s.y));
                fade = saturate(1.6 - px * 8.0);
                return tilt;
            }

            Varyings vert(Attributes input)
            {
                Varyings o = (Varyings)0;
                float3 positionWS = TransformObjectToWorld(input.positionOS.xyz);
                float t = _Time.y * _WaveSpeed;
                float amp = saturate(input.color.r);
                float wave = WaveSum(positionWS.xz, t);
                positionWS.y += wave * _WaveHeight * amp;
                o.positionWS = positionWS;
                o.positionCS = TransformWorldToHClip(positionWS);
                o.facet = float4(positionWS.xz, saturate(input.color.g), saturate(input.color.b));
                o.depth = saturate(input.color.b);
                o.fogFactor = ComputeFogFactor(o.positionCS.z);
                o.wave = float2(wave, amp);
                #if defined(_ADDITIONAL_LIGHTS_VERTEX)
                // la normal de la cara solo existe en el fragment: se usa "arriba"
                o.vertexLight = VertexLighting(positionWS, half3(0, 1, 0));
                #endif
                return o;
            }

            half4 frag(Varyings input) : SV_Target
            {
                float t = _Time.y * _WaveSpeed;
                // normal plana por triángulo, siempre hacia arriba
                float3 n = normalize(cross(ddy(input.positionWS), ddx(input.positionWS)));
                n *= n.y < 0 ? -1.0 : 1.0;
                // las olas inclinan las caras < 8° (pendiente máx. 0.49 * _WaveHeight): casi no cambian la luz.
                // Se exagera la pendiente solo para sombrear; la geometría (y FloatingBob) no cambia.
                n = normalize(float3(n.x * _FacetBoost, n.y, n.z * _FacetBoost));
                // facetas finas animadas encima de las de la malla (menos en arroyos y arrozales, que son más calmos)
                float rippleId, rippleFade;
                float2 tilt = RippleTilt(input.positionWS.xz, t * _RippleSpeed, rippleId, rippleFade);
                float ripple = _RippleStrength * rippleFade * (0.35 + 0.65 * input.wave.y);
                n = normalize(n + float3(tilt.x, 0.0, tilt.y) * ripple);
                float3 v = normalize(GetWorldSpaceViewDir(input.positionWS));

                // color por profundidad (por cara, con un toque de variación según la ola)
                half depth = (half)saturate(input.facet.w * 0.85 + input.depth * 0.15);
                half3 col = lerp(_ShallowColor.rgb, _DeepColor.rgb, depth);
                // crestas más claras (tirando a turquesa) y valles más oscuros, por cara
                half crest = (half)(clamp(input.wave.x, -1.0, 1.0) * input.wave.y) * _CrestContrast;
                col *= 1.0h + crest;
                col = lerp(col, _CrestColor.rgb, saturate(crest) * 0.8h);
                // leve variación de tono por faceta fina (textura low-poly, se apaga de lejos)
                col *= 1.0h + (half)((rippleId - 0.5) * 0.12 * rippleFade);

                // luz: luna (con sombras) + ambiente + faroles
                float4 shadowCoord = TransformWorldToShadowCoord(input.positionWS);
                // misma atenuación por distancia de sombra que URP/Lit
                Light mainLight = GetMainLight(shadowCoord, input.positionWS, half4(1, 1, 1, 1));
                half shadow = mainLight.shadowAttenuation;
                half ndl = saturate(dot(n, mainLight.direction));
                half3 lighting = SampleSH(n) + mainLight.color * (0.35 + 0.65 * ndl) * lerp(0.6h, 1.0h, shadow);
                // la luna (Euler 48,-38) queda detrás de la cámara (yaw 0, pitch ~50): su reflejo real nunca llega
                // a la cámara. Para el brillo del agua se usa la luna espejada en azimut (delante, estilizado).
                half3 moonDir = half3(-mainLight.direction.x, mainLight.direction.y, -mainLight.direction.z);
                half3 h = normalize(moonDir + v);
                half spec = pow(saturate(dot(n, h)), _Gloss) * _SpecStrength * shadow;
                half3 specular = mainLight.color * spec;

                #if defined(_ADDITIONAL_LIGHTS)
                InputData inputData = (InputData)0;
                inputData.positionWS = input.positionWS;
                inputData.normalWS = n;
                inputData.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(input.positionCS);
                uint lightCount = GetAdditionalLightsCount();
                #if USE_CLUSTER_LIGHT_LOOP
                // Forward+: las direccionales extra no están en los clusters
                [loop] for (uint dirIndex = 0u; dirIndex < min(URP_FP_DIRECTIONAL_LIGHTS_COUNT, MAX_VISIBLE_LIGHTS); dirIndex++)
                {
                    Light dl = GetAdditionalLight(dirIndex, input.positionWS, half4(1, 1, 1, 1));
                    half3 dlc = dl.color * dl.distanceAttenuation;
                    lighting += dlc * saturate(dot(n, dl.direction)) * 0.5h;
                    specular += dlc * pow(saturate(dot(n, normalize(dl.direction + v))), _Gloss * 0.5h) * _SpecStrength;
                }
                #endif
                LIGHT_LOOP_BEGIN(lightCount)
                    Light light = GetAdditionalLight(lightIndex, input.positionWS, half4(1, 1, 1, 1));
                    half3 lc = light.color * light.distanceAttenuation;
                    lighting += lc * saturate(dot(n, light.direction)) * 0.5h;
                    half3 hl = normalize(light.direction + v);
                    specular += lc * pow(saturate(dot(n, hl)), _Gloss * 0.5h) * _SpecStrength;
                LIGHT_LOOP_END
                #endif
                #if defined(_ADDITIONAL_LIGHTS_VERTEX)
                lighting += input.vertexLight * 0.5h;
                #endif

                half3 color = col * lighting;
                // reflejo del cielo: con la cámara a ~50° pow 4 daba ~0; pow 2 hace que cada faceta lo refleje distinto
                half fres = pow(1.0h - saturate(dot(n, v)), 2.0h);
                color = lerp(color, _SkyColor.rgb, fres * 0.6h);
                color += specular;

                // destellos: algunas caras brillan un instante
                float cell = Hash(floor(input.facet.xy * 0.75));
                // _SparkleAmount = fracción del tiempo que cada celda brilla (0.06 -> 6 %)
                float thr = cos(PI * _SparkleAmount);
                half tw = (half)saturate((sin(t * (1.3 + cell * 2.2) + cell * 47.0) - thr) / max(1.0 - thr, 1e-4));
                color += _SparkleColor.rgb * mainLight.color * tw * (1.0h - depth * 0.3h) * lerp(0.4h, 1.0h, shadow);

                // espuma por triángulo: late con las olas y avanza hacia la orilla
                half shore = (half)input.facet.z;
                half pulse = (half)(sin(t * 1.6 + dot(input.facet.xy, float2(0.31, 0.47))) * 0.5 + 0.5);
                half band = (half)frac(shore * 2.2 - t * 0.22);
                half foam = step(_FoamThreshold, shore + pulse * 0.18h) + step(0.92h, band) * step(0.3h, shore);
                foam = saturate(foam);
                // poca luz propia: en sombra la espuma no brilla como si fuera emisiva
                color = lerp(color, _FoamColor.rgb * (lighting * 0.85h + 0.1h), foam);

                half alpha = lerp(_AlphaShallow, _AlphaDeep, depth);
                alpha = max(alpha, foam * 0.95h);
                color = MixFog(color, input.fogFactor);
                return half4(color, alpha);
            }
            ENDHLSL
        }
    }

    FallBack Off
}
