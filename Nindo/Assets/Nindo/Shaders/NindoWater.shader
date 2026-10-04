// Agua low-poly animada de Nindō (URP).
//  * Olas: suma de 3 senos direccionales en el vertex shader (misma fórmula que la vista previa de
//    Tools/Blender/world/build_world.py -> wave_height). La amplitud por vértice viene en color.r.
//  * Facetas: la normal se reconstruye por triángulo con ddx/ddy, así cada cara refleja la luna
//    por separado y el agua "titila" cuando se mueve.
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
        _AlphaShallow ("Opacidad en lo bajo", Range(0, 1)) = 0.55
        _AlphaDeep ("Opacidad en lo hondo", Range(0, 1)) = 0.92
        _WaveHeight ("Altura de las olas", Range(0, 1)) = 0.18
        _WaveSpeed ("Velocidad de las olas", Range(0, 4)) = 1.0
        _Gloss ("Brillo especular", Range(4, 256)) = 48
        _SpecStrength ("Intensidad especular", Range(0, 4)) = 1.4
        _FoamThreshold ("Umbral de espuma", Range(0, 1)) = 0.72
        _SparkleAmount ("Cantidad de destellos", Range(0, 1)) = 0.06
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
                half _AlphaShallow;
                half _AlphaDeep;
                float _WaveHeight;
                float _WaveSpeed;
                half _Gloss;
                half _SpecStrength;
                half _FoamThreshold;
                half _SparkleAmount;
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
            };

            // misma fórmula que wave_height() en build_world.py
            float WaveHeight(float2 xz, float t)
            {
                float h = 0.55 * sin(dot(float2(0.958, 0.287), xz) * 0.35 + t * 1.1)
                        + 0.30 * sin(dot(float2(-0.371, 0.928), xz) * 0.55 + t * 1.5)
                        + 0.15 * sin(dot(float2(0.659, -0.753), xz) * 0.90 + t * 2.1);
                return h * _WaveHeight;
            }

            float Hash(float2 p)
            {
                return frac(sin(dot(p, float2(12.9898, 78.233))) * 43758.5453);
            }

            Varyings vert(Attributes input)
            {
                Varyings o = (Varyings)0;
                float3 positionWS = TransformObjectToWorld(input.positionOS.xyz);
                float t = _Time.y * _WaveSpeed;
                float amp = saturate(input.color.r);
                positionWS.y += WaveHeight(positionWS.xz, t) * amp;
                o.positionWS = positionWS;
                o.positionCS = TransformWorldToHClip(positionWS);
                o.facet = float4(positionWS.xz, saturate(input.color.g), saturate(input.color.b));
                o.depth = saturate(input.color.b);
                o.fogFactor = ComputeFogFactor(o.positionCS.z);
                return o;
            }

            half4 frag(Varyings input) : SV_Target
            {
                float t = _Time.y * _WaveSpeed;
                // normal plana por triángulo, siempre hacia arriba
                float3 n = normalize(cross(ddy(input.positionWS), ddx(input.positionWS)));
                n *= n.y < 0 ? -1.0 : 1.0;
                float3 v = normalize(GetWorldSpaceViewDir(input.positionWS));

                // color por profundidad (por cara, con un toque de variación según la ola)
                half depth = (half)saturate(input.facet.w * 0.85 + input.depth * 0.15);
                half3 col = lerp(_ShallowColor.rgb, _DeepColor.rgb, depth);

                // luz: luna (con sombras) + ambiente + faroles
                float4 shadowCoord = TransformWorldToShadowCoord(input.positionWS);
                Light mainLight = GetMainLight(shadowCoord);
                half shadow = mainLight.shadowAttenuation;
                half ndl = saturate(dot(n, mainLight.direction));
                half3 lighting = SampleSH(n) + mainLight.color * (0.35 + 0.65 * ndl) * lerp(0.6h, 1.0h, shadow);
                half3 h = normalize(mainLight.direction + v);
                half spec = pow(saturate(dot(n, h)), _Gloss) * _SpecStrength * shadow;
                half3 specular = mainLight.color * spec;

                #if defined(_ADDITIONAL_LIGHTS)
                InputData inputData = (InputData)0;
                inputData.positionWS = input.positionWS;
                inputData.normalWS = n;
                inputData.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(input.positionCS);
                uint lightCount = GetAdditionalLightsCount();
                LIGHT_LOOP_BEGIN(lightCount)
                    Light light = GetAdditionalLight(lightIndex, input.positionWS, half4(1, 1, 1, 1));
                    half3 lc = light.color * light.distanceAttenuation;
                    lighting += lc * saturate(dot(n, light.direction)) * 0.5h;
                    half3 hl = normalize(light.direction + v);
                    specular += lc * pow(saturate(dot(n, hl)), _Gloss * 0.5h) * _SpecStrength;
                LIGHT_LOOP_END
                #endif

                half3 color = col * lighting;
                // reflejo del cielo en ángulos rasantes
                half fres = pow(1.0h - saturate(dot(n, v)), 4.0h);
                color = lerp(color, _SkyColor.rgb, fres * 0.55h);
                color += specular;

                // destellos: algunas caras brillan un instante
                float cell = Hash(floor(input.facet.xy * 0.75));
                half tw = (half)saturate((sin(t * (1.3 + cell * 2.2) + cell * 47.0) - (1.0 - _SparkleAmount)) / max(_SparkleAmount, 1e-3));
                color += _SparkleColor.rgb * tw * (1.0h - depth * 0.3h) * lerp(0.4h, 1.0h, shadow);

                // espuma por triángulo: late con las olas y avanza hacia la orilla
                half shore = (half)input.facet.z;
                half pulse = (half)(sin(t * 1.6 + dot(input.facet.xy, float2(0.31, 0.47))) * 0.5 + 0.5);
                half band = (half)frac(shore * 2.2 - t * 0.22);
                half foam = step(_FoamThreshold, shore + pulse * 0.18h) + step(0.92h, band) * step(0.3h, shore);
                foam = saturate(foam);
                color = lerp(color, _FoamColor.rgb * (lighting * 0.6h + 0.4h), foam);

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
