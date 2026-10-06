// Cortina de agua de la Cascada Kohan (y de los chorros/pilares de agua que quieran reusarla). Malla generada
// por FX/KohanFalls.cs a partir de los labios del manifest; cada vértice trae:
//   color.r = avance de la caída (0 labio .. 1 pozo)   color.g = cercanía al borde lateral de la tira (0..1)
//   color.b = azar por columna                         color.a = capa (0 cortina de atrás, 1 tiras de adelante)
//   uv.x = metros a lo largo del labio                 uv.y = segundos de vuelo (negativo = el agua antes del labio)
// Las filas están repartidas parejo en TIEMPO de vuelo: las vetas que corren en uv.y se estiran solas a medida
// que el agua acelera, como en una cascada real.
// Look: flujo plano posterizado en 3 tonos con cortes duros (hondo / medio / espuma) como el resto de Nindō; la
// espuma pasa del 15 % en el labio al 75 % abajo (el agua se airea al caer). Labio vidrioso con una línea de luna,
// borde lateral roto en tinta, facetas que agarran la luna (normal por ddx/ddy) y destellos. La espuma tiene
// un poco de luz propia para que la cortina se lea de noche contra el basalto.
// _FlowPhase = segundos de flujo acumulados en C# (dt * caudal): con _Time.y * velocidad, cada cambio de caudal
// saltaba la fase Time.time * delta y las vetas corrían cientos de veces más rápido (o hacia arriba) un instante.
// _Intensity (1 fase 1, 1.4 crecida) sube la espuma y la turbulencia; _Corrupt tiñe de violeta la parte alta
// (el sello del clan en la transición de fase).
Shader "Nindo/Waterfall"
{
    Properties
    {
        _DeepColor ("Agua honda (labio)", Color) = (0.122, 0.29, 0.369, 1)
        _MidColor ("Agua media", Color) = (0.247, 0.498, 0.561, 1)
        _FoamColor ("Espuma", Color) = (0.91, 0.957, 0.965, 1)
        _GlowColor ("Luz propia de la espuma", Color) = (0.812, 0.902, 1, 1)
        _InkColor ("Tinta del borde", Color) = (0.07, 0.12, 0.16, 1)
        _CorruptTint ("Tinte del sello", Color) = (0.55, 0.25, 0.75, 1)
        _FlowPhase ("Fase del flujo (s)", Float) = 0
        _Turbulence ("Turbulencia", Range(0, 2)) = 1
        _Intensity ("Intensidad (crecida)", Range(0.5, 2)) = 1
        _Corrupt ("Corrupción", Range(0, 1)) = 0
        _FoamLip ("Espuma en el labio", Range(0, 1)) = 0.15
        _FoamBase ("Espuma abajo", Range(0, 1)) = 0.75
        _StreakDensity ("Vetas por metro", Range(0.5, 6)) = 2.4
        _Sway ("Vaivén del viento (m)", Range(0, 1)) = 0.3
        _Gloss ("Brillo de las facetas", Range(4, 128)) = 28
        _SpecStrength ("Intensidad del brillo", Range(0, 3)) = 0.9
        _Alpha ("Opacidad", Range(0, 1)) = 1
    }

    SubShader
    {
        Tags { "RenderType" = "Transparent" "Queue" = "Transparent-5" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }
        LOD 200

        Pass
        {
            Name "Waterfall"
            Tags { "LightMode" = "UniversalForward" }
            Blend SrcAlpha OneMinusSrcAlpha
            ZWrite Off
            Cull Off

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
                half4 _DeepColor, _MidColor, _FoamColor, _GlowColor, _InkColor, _CorruptTint;
                float _FlowPhase, _Turbulence, _Intensity, _Corrupt, _FoamLip, _FoamBase, _StreakDensity, _Sway;
                half _Gloss, _SpecStrength, _Alpha;
            CBUFFER_END

            // viento de la cascada (xz = dirección * fuerza, w = ráfaga 0..1): lo publica KohanFalls
            float4 _NindoFallsWind;

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                float4 color : COLOR;
                float2 uv : TEXCOORD0;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float4 data : TEXCOORD1;      // x avance, y borde, z azar, w capa
                float2 uv : TEXCOORD2;
                float fogFactor : TEXCOORD3;
                #if defined(_ADDITIONAL_LIGHTS_VERTEX)
                half3 vertexLight : TEXCOORD4;
                #endif
            };

            float Hash(float2 p) { return frac(sin(dot(p, float2(12.9898, 78.233))) * 43758.5453); }

            // ruido de valor 2D (celdas bilineales): las vetas salen de cortarlo con umbrales duros
            float VNoise(float2 p)
            {
                float2 i = floor(p), f = frac(p);
                f = f * f * (3.0 - 2.0 * f);
                float a = Hash(i), b = Hash(i + float2(1, 0)), c = Hash(i + float2(0, 1)), d = Hash(i + float2(1, 1));
                return lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y);
            }

            Varyings vert(Attributes input)
            {
                Varyings o = (Varyings)0;
                float prog = saturate(input.color.r);
                float rnd = input.color.b;
                float t = _Time.y;
                float3 positionWS = TransformObjectToWorld(input.positionOS.xyz);
                float3 n = TransformObjectToWorldNormal(input.normalOS);
                // la lámina "respira": bultos que bajan con el agua, más grandes abajo
                float bulge = sin(input.uv.y * 9.0 - _FlowPhase * 6.0 + rnd * 6.2832) * lerp(0.05, 0.4, prog);
                positionWS += n * bulge * _Turbulence * lerp(1.0, 1.35, saturate(_Intensity - 1.0));
                // vaivén del viento que sale del pozo (crece hacia abajo; más fuerte en las ráfagas)
                float sway = _Sway * prog * (0.6 + 0.4 * sin(t * 0.9 + rnd * 3.0)) * (1.0 + 0.5 * _NindoFallsWind.w);
                positionWS.xz += _NindoFallsWind.xz * sway;
                o.positionWS = positionWS;
                o.positionCS = TransformWorldToHClip(positionWS);
                o.data = float4(prog, saturate(input.color.g), rnd, input.color.a);
                o.uv = input.uv;
                o.fogFactor = ComputeFogFactor(o.positionCS.z);
                #if defined(_ADDITIONAL_LIGHTS_VERTEX)
                o.vertexLight = VertexLighting(positionWS, n);
                #endif
                return o;
            }

            half4 frag(Varyings input) : SV_Target
            {
                float prog = input.data.x, edge = input.data.y, rnd = input.data.z, layer = input.data.w;
                float2 uv = input.uv;
                float t = _FlowPhase;
                float surge = saturate(_Intensity - 1.0);

                // ---- vetas: columnas de ~0.4 m con fase propia; corren con el agua (uv.y = segundos de vuelo)
                float colId = floor(uv.x * _StreakDensity);
                float colRnd = Hash(float2(colId, layer * 17.0 + 3.0));
                float flowY = (uv.y - t) * (1.5 + colRnd * 0.8);
                float n1 = VNoise(float2(uv.x * _StreakDensity * 1.3 + colRnd * 7.0, flowY));
                float n2 = VNoise(float2(uv.x * _StreakDensity * 3.1 + 11.0, flowY * 2.3 + colRnd * 5.0));
                float v = n1 * 0.7 + n2 * 0.3;
                // espuma: del 15 % al 75 % (más en la crecida y en las tiras de adelante, que son más aireadas)
                float share = lerp(_FoamLip, _FoamBase, smoothstep(0.0, 0.85, prog)) + surge * 0.25 + layer * 0.1;
                float foam = step(1.0 - saturate(share), v);
                float deep = step(v, 0.28 * (1.0 - prog));          // vetas hondas que se van apagando al caer
                half3 col = lerp(lerp(_MidColor.rgb, _DeepColor.rgb, deep), _FoamColor.rgb, foam);
                // labio vidrioso: banda honda con una línea de luna justo en el borde
                float lip = step(prog, 0.05) * step(-0.001, uv.y) + step(uv.y, -0.001);
                col = lerp(col, _DeepColor.rgb, lip * (1.0 - foam * 0.6));
                float moonLine = step(abs(uv.y + 0.02), 0.035);
                col = lerp(col, _GlowColor.rgb, moonLine * 0.85);
                foam = max(foam * (1.0 - lip), moonLine * 0.6);
                // la cortina de atrás un poco más honda: separa las capas en profundidad
                col *= lerp(0.86, 1.0, layer);

                // ---- luz: facetas planas (ddx/ddy) iluminadas por la luna, ambiente y las luces del pozo
                float3 nf = normalize(cross(ddy(input.positionWS), ddx(input.positionWS)));
                float3 v3 = normalize(GetWorldSpaceViewDir(input.positionWS));
                nf *= dot(nf, v3) < 0.0 ? -1.0 : 1.0;
                Light mainLight = GetMainLight();
                half ndl = saturate(dot(nf, mainLight.direction));
                half3 lighting = SampleSH(nf) + mainLight.color * (0.45h + 0.55h * ndl);
                half3 h = normalize(mainLight.direction + v3);
                half spec = pow(saturate(dot(nf, h)), _Gloss) * _SpecStrength;
                half3 specular = mainLight.color * spec * (0.4h + 0.6h * (half)foam);
                #if defined(_ADDITIONAL_LIGHTS)
                InputData inputData = (InputData)0;
                inputData.positionWS = input.positionWS;
                inputData.normalWS = nf;
                inputData.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(input.positionCS);
                uint lightCount = GetAdditionalLightsCount();
                #if USE_CLUSTER_LIGHT_LOOP
                [loop] for (uint dirIndex = 0u; dirIndex < min(URP_FP_DIRECTIONAL_LIGHTS_COUNT, MAX_VISIBLE_LIGHTS); dirIndex++)
                {
                    Light dl = GetAdditionalLight(dirIndex, input.positionWS, half4(1, 1, 1, 1));
                    lighting += dl.color * dl.distanceAttenuation * (0.4h + 0.6h * saturate(dot(nf, dl.direction)));
                }
                #endif
                LIGHT_LOOP_BEGIN(lightCount)
                    Light light = GetAdditionalLight(lightIndex, input.positionWS, half4(1, 1, 1, 1));
                    // el agua deja pasar la luz: media lambert, así la luz fría del pozo la ilumina de los dos lados
                    lighting += light.color * light.distanceAttenuation * (0.4h + 0.6h * saturate(dot(nf, light.direction)));
                LIGHT_LOOP_END
                #endif
                #if defined(_ADDITIONAL_LIGHTS_VERTEX)
                lighting += input.vertexLight;
                #endif

                // tope: la luz de relleno de la cascada (intensidad 48) sumada sin límite quemaba el agua en blanco
                lighting = min(lighting, half3(2.0h, 2.0h, 2.0h));
                half3 color = col * lighting + specular;
                // luz propia de la espuma (se lee de noche) y destellos sueltos que bajan con el agua
                color += _GlowColor.rgb * (half)foam * 0.25h;
                float cell = Hash(floor(float2(uv.x * 2.0, (uv.y - t) * 3.0)));
                half tw = (half)step(0.985, cell) * (half)step(0.5, sin(_Time.y * (4.0 + cell * 6.0) + cell * 40.0));
                color += _GlowColor.rgb * mainLight.color * tw * 0.8h;
                // sello del clan: violeta cerca del labio durante la transición
                color = lerp(color, _CorruptTint.rgb * (lighting * 0.6h + 0.25h), _Corrupt * (1.0 - prog) * (1.0 - prog));

                // ---- borde lateral roto en tinta y disolución abajo, entre la espuma del pozo
                float ragged = VNoise(float2(uv.x * 4.0, (uv.y - t) * 2.0 + rnd * 9.0));
                float inkEdge = step(0.62 + ragged * 0.25, edge);
                color = lerp(color, _InkColor.rgb * lighting, inkEdge * 0.75);
                clip(0.93 + ragged * 0.07 - edge);
                clip((1.02 - prog) * 14.0 - ragged * 0.9);

                half alpha = lerp(0.9h, 0.78h, (half)layer);
                alpha = max(alpha, (half)foam);
                alpha *= _Alpha;
                color = MixFog(color, input.fogFactor);
                return half4(color, alpha);
            }
            ENDHLSL
        }
    }

    FallBack Off
}
