// Agua con espuma de la arena del lago. Mallas generadas por FX/KohanFalls.cs y FX/FloodSheet.cs.
//  _Mode 0  pozo de la cascada (encima del lago): hervor de espuma en la línea de caída, anillos que se alejan
//           torcidos en espiral, collar de espuma en las rocas y agua aireada (turquesa blanquecino) cerca de la
//           caída. uv.x = metros desde la línea de caída (+ hacia la arena), uv.y = metros a lo largo de ella.
//           Ondula con la MISMA suma de senos que Nindo/Water Lowpoly para no hundirse entre sus olas.
//  _Mode 1  capa de agua sobre la plataforma (crecida de la fase 2, o la película mojada de la llovizna):
//           espuma en las barandas, anillos en los puntos que pide FloodSheet.Ripple y anillitos de llovizna.
//           uv.x = metros hasta el borde de la plataforma.
//  _Mode 2  cintas de espuma del desagüe que rodean la plataforma: uv.x = 0..1 de lado a lado, uv.y = metros.
// color.a de cada vértice apaga los extremos (puntas del pozo, cola de las cintas).
// Todo posterizado con cortes duros (espuma sí/no), como el agua del lago.
// Lo que corre con el caudal usa _FlowPhase (segundos de flujo acumulados en C#), no _Time.y * _Flow: así un
// cambio de caudal acelera el agua en vez de saltar la fase. _Flow solo decide cuánta espuma hay.
Shader "Nindo/Foam Water"
{
    Properties
    {
        _Mode ("0 pozo, 1 crecida, 2 cinta", Float) = 0
        _WaterColor ("Agua aireada", Color) = (0.247, 0.498, 0.561, 1)
        _FoamColor ("Espuma", Color) = (0.91, 0.957, 0.965, 1)
        _SkyColor ("Reflejo del cielo", Color) = (0.2, 0.3, 0.48, 1)
        _Alpha ("Opacidad", Range(0, 1)) = 1
        _Flow ("Intensidad (crecida)", Range(0, 2)) = 1
        _FlowPhase ("Fase del flujo (s)", Float) = 0
        _Level ("Crecida (0..1)", Range(0, 1)) = 0
        _Wet ("Película mojada (0..1)", Range(0, 1)) = 0
        _WaveHeight ("Altura de las olas del lago", Float) = 0.26
        _WaveSpeed ("Velocidad de las olas del lago", Float) = 1
        _Rock0 ("Roca 0 (xyz, radio)", Vector) = (0, -999, 0, 0)
        _Rock1 ("Roca 1", Vector) = (0, -999, 0, 0)
        _Rock2 ("Roca 2", Vector) = (0, -999, 0, 0)
        _Rock3 ("Roca 3", Vector) = (0, -999, 0, 0)
        _Ripple0 ("Onda 0 (xyz, inicio)", Vector) = (0, 0, 0, -99)
        _Ripple1 ("Onda 1", Vector) = (0, 0, 0, -99)
        _Ripple2 ("Onda 2", Vector) = (0, 0, 0, -99)
        _Ripple3 ("Onda 3", Vector) = (0, 0, 0, -99)
        _Ripple4 ("Onda 4", Vector) = (0, 0, 0, -99)
        _Ripple5 ("Onda 5", Vector) = (0, 0, 0, -99)
        _Spray ("Origen de la llovizna (xyz, radio; radio 0 = pareja)", Vector) = (0, 0, 0, 0)
    }

    SubShader
    {
        Tags { "RenderType" = "Transparent" "Queue" = "Transparent-8" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }

        Pass
        {
            Name "FoamWater"
            Tags { "LightMode" = "UniversalForward" }
            Blend SrcAlpha OneMinusSrcAlpha
            ZWrite Off
            Cull Back

            HLSLPROGRAM
            #pragma target 3.5
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
            #pragma multi_compile _ _CLUSTER_LIGHT_LOOP
            #pragma multi_compile_fog
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            CBUFFER_START(UnityPerMaterial)
                float _Mode;
                half4 _WaterColor, _FoamColor, _SkyColor;
                half _Alpha;
                float _Flow, _FlowPhase, _Level, _Wet, _WaveHeight, _WaveSpeed;
                float4 _Rock0, _Rock1, _Rock2, _Rock3;
                float4 _Ripple0, _Ripple1, _Ripple2, _Ripple3, _Ripple4, _Ripple5;
                float4 _Spray;
            CBUFFER_END

            struct Attributes { float4 positionOS : POSITION; float2 uv : TEXCOORD0; half4 color : COLOR; };
            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float2 uv : TEXCOORD1;
                float fogFactor : TEXCOORD2;
                half fade : TEXCOORD3;
                #if defined(_ADDITIONAL_LIGHTS_VERTEX)
                half3 vertexLight : TEXCOORD4;
                #endif
            };

            float Hash(float2 p) { return frac(sin(dot(p, float2(12.9898, 78.233))) * 43758.5453); }
            float VNoise(float2 p)
            {
                float2 i = floor(p), f = frac(p);
                f = f * f * (3.0 - 2.0 * f);
                return lerp(lerp(Hash(i), Hash(i + float2(1, 0)), f.x), lerp(Hash(i + float2(0, 1)), Hash(i + float2(1, 1)), f.x), f.y);
            }

            // = WaveSum de Nindo/Water Lowpoly (y de build_world.wave_height): el pozo sube y baja con el lago
            float WaveSum(float2 xz, float t)
            {
                return 0.55 * sin(dot(float2(0.958, 0.287), xz) * 0.35 + t * 1.1)
                     + 0.30 * sin(dot(float2(-0.371, 0.928), xz) * 0.55 + t * 1.5)
                     + 0.15 * sin(dot(float2(0.659, -0.753), xz) * 0.90 + t * 2.1);
            }

            float RockFoam(float2 p, float4 r, float n)
            {
                float d = distance(p, r.xz) - r.w;
                return step(d, 0.45 + n * 0.45) * step(-0.3, d);
            }

            float RippleRing(float2 p, float4 r, float t)
            {
                float age = t - r.w;
                float d = distance(p, r.xz);
                float rad = age * 2.4;
                return step(abs(d - rad), 0.07 + age * 0.03) * saturate(1.0 - age / 1.3) * step(0.0, age);
            }

            Varyings vert(Attributes input)
            {
                Varyings o = (Varyings)0;
                float3 positionWS = TransformObjectToWorld(input.positionOS.xyz);
                if (_Mode < 0.5 || _Mode > 1.5)     // el pozo y las cintas van sobre el lago
                    positionWS.y += WaveSum(positionWS.xz, _Time.y * _WaveSpeed) * _WaveHeight;
                o.positionWS = positionWS;
                o.positionCS = TransformWorldToHClip(positionWS);
                o.uv = input.uv;
                o.fogFactor = ComputeFogFactor(o.positionCS.z);
                o.fade = input.color.a;
                #if defined(_ADDITIONAL_LIGHTS_VERTEX)
                o.vertexLight = VertexLighting(positionWS, half3(0, 1, 0));
                #endif
                return o;
            }

            half4 frag(Varyings input) : SV_Target
            {
                float t = _Time.y;
                float ph = _FlowPhase;
                float2 p = input.positionWS.xz;
                float2 uv = input.uv;
                half foam = 0.0h;
                half water = 0.0h;           // alfa del agua sin espuma
                half chop = 0.0h;            // facetas claras que corren: agua picada junto a la caída
                half crest = 1.0h;           // 1 = espuma blanca de cresta, 0 = espuma aireada (azulada)
                if (_Mode < 0.5)
                {
                    float d = uv.x;
                    // hervor: celdas que se dan vuelta rápido sobre la caída (y detrás, contra la roca)
                    float boil = VNoise(p * 0.9 + float2(sin(t * 0.7), -ph * 1.6));
                    float boil2 = VNoise(p * 2.1 - float2(ph * 0.9, ph * 1.3));
                    float bv = boil * 0.7 + boil2 * 0.3;
                    // vetas que se alejan de la caída: el hervor corre hacia afuera en vez de quedarse quieto
                    float streak = VNoise(float2(uv.y * 1.4, d * 0.35 - ph * 1.1));
                    bv = bv * 0.75 + streak * 0.25;
                    // en la crecida el hervor cubre más (umbral más bajo). Con 0.3 cerca de la caída el ~80 % era espuma
                    // pareja de 3-4 m de ancho, blanca y quieta: desde la cámara de juego un campo nevado con las rocas
                    // encima. Ahora la espuma es una franja rota pegada a la caída y entre las celdas se ve agua
                    float thr = 0.4 - 0.12 * saturate(_Flow - 1.0) + 0.5 * smoothstep(-1.0, 1.8, abs(d - 0.2));
                    foam = (half)step(thr, bv);
                    // dos tonos posterizados: solo el corazón del hervor es blanco; el borde es espuma aireada azulada
                    crest = (half)step(thr + 0.14, bv);
                    // anillos que se alejan, torcidos por el rumbo: espirales de espuma como en el arte conceptual
                    float wob = VNoise(p * 0.35 + 3.7) * 0.35;
                    float band = frac(d * 0.19 - ph * 0.3 + uv.y * 0.022 + wob);
                    float w = 0.2 * exp(-max(d, 0.0) / 6.5);
                    half ring = (half)(step(band, w) * step(0.38, VNoise(float2(uv.y * 0.45, d * 0.6) + 11.0)) * step(0.4, d));
                    crest = max(crest * foam, ring * (half)step(d, 2.5));
                    foam = max(foam, ring);
                    float rn = VNoise(p * 1.7 + t * 0.6);
                    half rock = (half)max(max(RockFoam(p, _Rock0, rn), RockFoam(p, _Rock1, rn)), max(RockFoam(p, _Rock2, rn), RockFoam(p, _Rock3, rn)));
                    foam = max(foam, rock);
                    crest = max(crest, rock);
                    water = (half)(0.42 * exp(-max(d, 0.0) / 3.2));
                    chop = (half)step(0.56, VNoise(p * 1.3 + float2(ph * 1.1, -ph * 0.8))) * (half)saturate(water * 2.5);
                    half fade = (half)(1.0 - smoothstep(8.0, 13.0, d));
                    foam *= fade;
                    water *= fade;
                }
                else if (_Mode < 1.5)
                {
                    float edge = uv.x;
                    float n = VNoise(p * 1.6 + float2(t * 0.4, -t * 0.3));
                    // espuma en las barandas: el agua choca contra los postes
                    foam = (half)(step(edge, 0.25 + 0.35 * n) * step(0.2, _Level));
                    float rr = max(max(RippleRing(p, _Ripple0, t), RippleRing(p, _Ripple1, t)),
                                   max(max(RippleRing(p, _Ripple2, t), RippleRing(p, _Ripple3, t)), max(RippleRing(p, _Ripple4, t), RippleRing(p, _Ripple5, t))));
                    foam = max(foam, (half)rr * (half)saturate(_Level * 2.0 + _Wet));
                    // anillitos de la llovizna: celdas de 0.9 m que se encienden de vez en cuando (~35 por segundo en toda la plataforma)
                    float2 cell = floor(p / 0.9);
                    float ph = Hash(cell);
                    float slot = floor(t * 0.9 + ph);
                    float on = step(Hash(cell + slot * 0.137), 0.1);
                    float2 c = (cell + 0.2 + 0.6 * float2(Hash(cell + slot), Hash(cell - slot))) * 0.9;
                    float age = frac(t * 0.9 + ph);
                    float ring = step(abs(distance(p, c) - age * 0.45), 0.025) * (1.0 - age) * on;
                    // la película mojada y su llovizna se concentran del lado de la cascada
                    float near = _Spray.w > 0.0 ? 1.0 - smoothstep(_Spray.w * 0.35, _Spray.w, distance(p, _Spray.xz)) : 1.0;
                    float wet = _Wet * near;
                    foam = max(foam, (half)(ring * step(Hash(cell * 1.7 + slot), near)) * (half)saturate(wet + _Level));
                    water = (half)(wet * 0.16 + _Level * 0.42);
                }
                else
                {
                    float across = abs(uv.x * 2.0 - 1.0);
                    float n = VNoise(float2(uv.x * 5.0, (uv.y - ph * 1.2) * 0.7));
                    foam = (half)(step(0.56 + across * across * 0.4, n));
                    water = 0.0h;
                }

                // luz: el agua mira arriba; la espuma con un poco de luz propia
                Light mainLight = GetMainLight();
                half3 lighting = SampleSH(half3(0, 1, 0)) + mainLight.color * (0.45h + 0.55h * saturate(mainLight.direction.y));
                #if defined(_ADDITIONAL_LIGHTS)
                InputData inputData = (InputData)0;
                inputData.positionWS = input.positionWS;
                inputData.normalWS = half3(0, 1, 0);
                inputData.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(input.positionCS);
                uint lightCount = GetAdditionalLightsCount();
                #if USE_CLUSTER_LIGHT_LOOP
                [loop] for (uint dirIndex = 0u; dirIndex < min(URP_FP_DIRECTIONAL_LIGHTS_COUNT, MAX_VISIBLE_LIGHTS); dirIndex++)
                {
                    Light dl = GetAdditionalLight(dirIndex, input.positionWS, half4(1, 1, 1, 1));
                    lighting += dl.color * dl.distanceAttenuation * saturate(dl.direction.y);
                }
                #endif
                LIGHT_LOOP_BEGIN(lightCount)
                    Light light = GetAdditionalLight(lightIndex, input.positionWS, half4(1, 1, 1, 1));
                    lighting += light.color * light.distanceAttenuation * (0.3h + 0.7h * saturate(light.direction.y));
                LIGHT_LOOP_END
                #endif
                #if defined(_ADDITIONAL_LIGHTS_VERTEX)
                lighting += input.vertexLight;
                #endif
                // tope: la luz de contorno de la cascada es fuerte (para que se note sobre los personajes) y sumada sin
                // límite convertía la película mojada (9 % de opacidad) en una placa celeste que tapaba la plataforma
                lighting = min(lighting, half3(1.6h, 1.6h, 1.6h));
                float3 v = normalize(GetWorldSpaceViewDir(input.positionWS));
                half fres = (half)pow(1.0 - saturate(v.y), 2.0);
                half3 waterCol = lerp(_WaterColor.rgb * lighting * (1.0h + 0.45h * chop), _SkyColor.rgb, fres * 0.5h);
                // la espuma aireada toma el color del agua: la blanca pareja se leía como nieve
                half3 foamCol = lerp(lerp(_FoamColor.rgb, _WaterColor.rgb, 0.45h) * 1.15h, _FoamColor.rgb, crest);
                half3 color = lerp(waterCol, foamCol * (lighting * 0.8h + 0.14h), foam);
                half alpha = max(water, foam * 0.92h) * _Alpha * input.fade;
                color = MixFog(color, input.fogFactor);
                return half4(color, alpha);
            }
            ENDHLSL
        }
    }

    FallBack Off
}
