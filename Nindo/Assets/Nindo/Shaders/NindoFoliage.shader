// Follaje de Nindō: color de paleta + iluminación simple (luna con sombras, faroles, ambiente,
// niebla) + balanceo por viento en el vertex shader. El peso del viento viene en el canal R del
// color de vértice (0 = tronco/base fija, 1 = punta de la hoja), lo escriben los scripts de Blender
// (llega a Unity en lineal: WindWeight() lo devuelve a 0..1).
// Si este shader no compilara en alguna versión de URP, WorldBuilder vuelve al material Lit.
Shader "Nindo/Foliage Wind"
{
    Properties
    {
        [MainTexture] _BaseMap ("Paleta", 2D) = "white" {}
        [MainColor] _BaseColor ("Color", Color) = (1, 1, 1, 1)
        _WindStrength ("Fuerza del viento", Range(0, 1)) = 0.14
        _WindSpeed ("Velocidad", Range(0, 5)) = 1.4
        _WindScale ("Escala de las ráfagas", Range(0.01, 1)) = 0.08
        _Flutter ("Aleteo", Range(0, 0.2)) = 0.03
        _Wrap ("Luz que atraviesa (wrap)", Range(0, 1)) = 0.35
    }

    SubShader
    {
        Tags { "RenderType" = "Opaque" "RenderPipeline" = "UniversalPipeline" "Queue" = "Geometry" }
        LOD 200
        Cull Off

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

        CBUFFER_START(UnityPerMaterial)
            float4 _BaseMap_ST;
            half4 _BaseColor;
            float _WindStrength;
            float _WindSpeed;
            float _WindScale;
            float _Flutter;
            half _Wrap;
        CBUFFER_END

        TEXTURE2D(_BaseMap);
        SAMPLER(sampler_BaseMap);

        // el peso se escribe con bmesh (byte sRGB 'crudo') y el FBX se exporta con colors_type LINEAR:
        // Unity recibe srgb_to_linear(peso) (0.5 -> 0.22). Se deshace aquí para recuperar el peso real.
        float WindWeight(float r)
        {
            r = saturate(r);
            return saturate(r <= 0.0031308 ? r * 12.92 : 1.055 * pow(r, 1.0 / 2.4) - 0.055);
        }

        // desplazamiento en espacio mundo (ráfaga lenta + aleteo rápido), ponderado por el peso
        float3 WindOffset(float3 positionWS, float weight)
        {
            float t = _Time.y * _WindSpeed;
            float phase = dot(positionWS.xz, float2(_WindScale, _WindScale * 0.73));
            float gust = sin(t + phase) * 0.6 + sin(t * 0.37 + phase * 0.5) * 0.4;
            float flutter = sin(t * 7.3 + positionWS.y * 3.1 + phase * 9.0) * _Flutter;
            float3 dir = normalize(float3(1.0, 0.0, 0.45));
            return (dir * (gust * _WindStrength + flutter) + float3(0, -abs(gust) * _WindStrength * 0.15, 0)) * weight;
        }
        ENDHLSL

        Pass
        {
            Name "ForwardLit"
            Tags { "LightMode" = "UniversalForward" }

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
            #pragma multi_compile _ _CLUSTER_LIGHT_LOOP
            #pragma multi_compile_fragment _ _SHADOWS_SOFT
            #pragma multi_compile_fog
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                float2 uv : TEXCOORD0;
                float4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
                float3 positionWS : TEXCOORD1;
                float3 normalWS : TEXCOORD2;
                float fogFactor : TEXCOORD3;
                #if defined(_ADDITIONAL_LIGHTS_VERTEX)
                half3 vertexLight : TEXCOORD4;   // faroles por vértice (calidad Baja / Muy baja)
                #endif
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings vert(Attributes input)
            {
                Varyings o = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_TRANSFER_INSTANCE_ID(input, o);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                float3 positionWS = TransformObjectToWorld(input.positionOS.xyz);
                positionWS += WindOffset(positionWS, WindWeight(input.color.r));
                o.positionWS = positionWS;
                o.positionCS = TransformWorldToHClip(positionWS);
                o.normalWS = TransformObjectToWorldNormal(input.normalOS);
                o.uv = TRANSFORM_TEX(input.uv, _BaseMap);
                o.fogFactor = ComputeFogFactor(o.positionCS.z);
                #if defined(_ADDITIONAL_LIGHTS_VERTEX)
                o.vertexLight = VertexLighting(positionWS, o.normalWS);
                #endif
                return o;
            }

            half3 Diffuse(Light light, half3 normalWS)
            {
                half ndl = dot(normalWS, light.direction);
                half wrapped = saturate((ndl + _Wrap) / (1.0h + _Wrap));
                return light.color * (wrapped * light.distanceAttenuation * light.shadowAttenuation);
            }

            half4 frag(Varyings input, FRONT_FACE_TYPE facing : FRONT_FACE_SEMANTIC) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(input);
                half4 albedo = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, input.uv) * _BaseColor;
                half3 normalWS = normalize(input.normalWS);
                normalWS = IS_FRONT_VFACE(facing, true, false) ? normalWS : -normalWS;

                InputData inputData = (InputData)0;
                inputData.positionWS = input.positionWS;
                inputData.normalWS = normalWS;
                inputData.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(input.positionCS);
                inputData.shadowCoord = TransformWorldToShadowCoord(input.positionWS);

                // misma atenuación por distancia de sombra que URP/Lit
                Light mainLight = GetMainLight(inputData.shadowCoord, input.positionWS, half4(1, 1, 1, 1));
                half3 lighting = Diffuse(mainLight, normalWS) + SampleSH(normalWS);

                #if defined(_ADDITIONAL_LIGHTS)
                uint lightCount = GetAdditionalLightsCount();
                #if USE_CLUSTER_LIGHT_LOOP
                // Forward+: las direccionales extra no están en los clusters
                [loop] for (uint dirIndex = 0u; dirIndex < min(URP_FP_DIRECTIONAL_LIGHTS_COUNT, MAX_VISIBLE_LIGHTS); dirIndex++)
                    lighting += Diffuse(GetAdditionalLight(dirIndex, input.positionWS, half4(1, 1, 1, 1)), normalWS);
                #endif
                LIGHT_LOOP_BEGIN(lightCount)
                    Light light = GetAdditionalLight(lightIndex, input.positionWS, half4(1, 1, 1, 1));
                    lighting += Diffuse(light, normalWS);
                LIGHT_LOOP_END
                #endif
                #if defined(_ADDITIONAL_LIGHTS_VERTEX)
                lighting += input.vertexLight;
                #endif

                half3 color = albedo.rgb * lighting;
                color = MixFog(color, input.fogFactor);
                return half4(color, 1.0h);
            }
            ENDHLSL
        }

        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode" = "ShadowCaster" }
            ZWrite On
            ZTest LEqual
            ColorMask 0

            HLSLPROGRAM
            #pragma vertex vertShadow
            #pragma fragment fragShadow
            #pragma multi_compile_vertex _ _CASTING_PUNCTUAL_LIGHT_SHADOW
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Shadows.hlsl"

            float3 _LightDirection;
            float3 _LightPosition;

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                float4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings { float4 positionCS : SV_POSITION; };

            Varyings vertShadow(Attributes input)
            {
                Varyings o;
                UNITY_SETUP_INSTANCE_ID(input);
                float3 positionWS = TransformObjectToWorld(input.positionOS.xyz);
                positionWS += WindOffset(positionWS, WindWeight(input.color.r));
                float3 normalWS = TransformObjectToWorldNormal(input.normalOS);
                #if defined(_CASTING_PUNCTUAL_LIGHT_SHADOW)
                    float3 lightDirectionWS = normalize(_LightPosition - positionWS);
                #else
                    float3 lightDirectionWS = _LightDirection;
                #endif
                float4 positionCS = TransformWorldToHClip(ApplyShadowBias(positionWS, normalWS, lightDirectionWS));
                #if UNITY_REVERSED_Z
                    positionCS.z = min(positionCS.z, UNITY_NEAR_CLIP_VALUE);
                #else
                    positionCS.z = max(positionCS.z, UNITY_NEAR_CLIP_VALUE);
                #endif
                o.positionCS = positionCS;
                return o;
            }

            half4 fragShadow(Varyings input) : SV_Target { return 0; }
            ENDHLSL
        }

        Pass
        {
            Name "DepthOnly"
            Tags { "LightMode" = "DepthOnly" }
            ZWrite On
            ColorMask R

            HLSLPROGRAM
            #pragma vertex vertDepth
            #pragma fragment fragDepth
            #pragma multi_compile_instancing

            struct Attributes
            {
                float4 positionOS : POSITION;
                float4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings { float4 positionCS : SV_POSITION; };

            Varyings vertDepth(Attributes input)
            {
                Varyings o;
                UNITY_SETUP_INSTANCE_ID(input);
                float3 positionWS = TransformObjectToWorld(input.positionOS.xyz);
                positionWS += WindOffset(positionWS, WindWeight(input.color.r));
                o.positionCS = TransformWorldToHClip(positionWS);
                return o;
            }

            half4 fragDepth(Varyings input) : SV_Target { return input.positionCS.z; }
            ENDHLSL
        }

        // sin este pass URP usaría el DepthNormals de Lit (por el FallBack), sin viento:
        // con SSAO o decals quedarían halos fijos alrededor de las hojas que se mueven
        Pass
        {
            Name "DepthNormals"
            Tags { "LightMode" = "DepthNormals" }
            ZWrite On

            HLSLPROGRAM
            #pragma vertex vertDepthNormals
            #pragma fragment fragDepthNormals
            #pragma multi_compile_instancing

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                float4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 normalWS : TEXCOORD0;
            };

            // mismo viento que ForwardLit/DepthOnly
            Varyings vertDepthNormals(Attributes input)
            {
                Varyings o;
                UNITY_SETUP_INSTANCE_ID(input);
                float3 positionWS = TransformObjectToWorld(input.positionOS.xyz);
                positionWS += WindOffset(positionWS, WindWeight(input.color.r));
                o.positionCS = TransformWorldToHClip(positionWS);
                o.normalWS = TransformObjectToWorldNormal(input.normalOS);
                return o;
            }

            half4 fragDepthNormals(Varyings input, FRONT_FACE_TYPE facing : FRONT_FACE_SEMANTIC) : SV_Target
            {
                // doble cara como en ForwardLit: la cara de atrás usa la normal invertida
                float3 n = normalize(input.normalWS);
                n = IS_FRONT_VFACE(facing, true, false) ? n : -n;
                return half4(n, 0.0);
            }
            ENDHLSL
        }
    }

    FallBack "Universal Render Pipeline/Lit"
}
