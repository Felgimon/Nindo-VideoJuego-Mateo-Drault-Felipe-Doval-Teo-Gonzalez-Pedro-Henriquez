// Rocío y espuma en bloques: partículas de malla facetada (gotas gordas, nubes de rocío, hervor del pozo,
// salpicones) en el lenguaje low-poly del resto del mundo. Opacas con recorte por tramado (Bayer 4x4) según el
// alfa de la partícula: se desvanecen sin ordenarse y casi sin sobre-dibujo (la niebla transparente de 5 m
// encima de la arena costaba mucho más). Caras planas por ddx/ddy, luz de luna + ambiente + luces cercanas
// (la luz fría del pozo las ilumina desde atrás) y un poco de luz propia para que se lean de noche.
// Como la niebla, se deshacen alrededor de Kaito y del jefe (_NindoPlayerPos / _NindoBossPos): el rocío que
// cruza la baranda norte nunca tapa a los que pelean. _ClearAmount 0 lo apaga: los salpicones del cuerpo del
// jefe (WaterSplash) nacen justo donde está él y se borrarían enteros.
Shader "Nindo/Spray"
{
    Properties
    {
        _Color ("Color", Color) = (0.91, 0.957, 0.965, 1)
        _Shade ("Color en sombra", Color) = (0.7, 0.79, 0.87, 1)
        _Glow ("Luz propia", Range(0, 1)) = 0.32
        _ClearAmount ("Despejar alrededor de los que pelean", Range(0, 1)) = 1
    }

    SubShader
    {
        Tags { "RenderType" = "TransparentCutout" "Queue" = "AlphaTest+10" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }

        Pass
        {
            Name "Spray"
            Tags { "LightMode" = "UniversalForward" }
            ZWrite On
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
                half4 _Color, _Shade;
                half _Glow;
                float _ClearAmount;
            CBUFFER_END

            float4 _NindoPlayerPos;
            float4 _NindoBossPos;

            struct Attributes { float4 positionOS : POSITION; float3 normalOS : NORMAL; half4 color : COLOR; };
            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                half4 color : TEXCOORD1;
                float fogFactor : TEXCOORD2;
                #if defined(_ADDITIONAL_LIGHTS_VERTEX)
                half3 vertexLight : TEXCOORD3;
                #endif
            };

            Varyings vert(Attributes input)
            {
                Varyings o = (Varyings)0;
                o.positionWS = TransformObjectToWorld(input.positionOS.xyz);
                o.positionCS = TransformWorldToHClip(o.positionWS);
                o.color = input.color;
                o.fogFactor = ComputeFogFactor(o.positionCS.z);
                #if defined(_ADDITIONAL_LIGHTS_VERTEX)
                o.vertexLight = VertexLighting(o.positionWS, TransformObjectToWorldNormal(input.normalOS));
                #endif
                return o;
            }

            half4 frag(Varyings input) : SV_Target
            {
                // tramado ordenado: el alfa de la partícula decide qué píxeles quedan
                static const float bayer[16] = { 0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5 };
                uint2 px = (uint2)input.positionCS.xy & 3u;
                float2 p = input.positionWS.xz;
                float clear = lerp(1.0, smoothstep(1.0, 2.4, distance(p, _NindoPlayerPos.xz)), saturate(_NindoPlayerPos.w));
                clear *= lerp(1.0, smoothstep(1.6, 3.6, distance(p, _NindoBossPos.xz)), saturate(_NindoBossPos.w));
                clear = lerp(1.0, clear, _ClearAmount);
                clip(input.color.a * clear - (bayer[px.y * 4u + px.x] + 0.5) / 16.0);

                float3 n = normalize(cross(ddy(input.positionWS), ddx(input.positionWS)));
                float3 v = normalize(GetWorldSpaceViewDir(input.positionWS));
                n *= dot(n, v) < 0.0 ? -1.0 : 1.0;
                Light mainLight = GetMainLight();
                half ndl = saturate(dot(n, mainLight.direction));
                // sombreado chato: el rocío deja pasar la luz (con mucho contraste parecían piedras grises)
                half3 albedo = lerp(_Shade.rgb, _Color.rgb, 0.55h + 0.45h * ndl) * input.color.rgb;
                half3 lighting = SampleSH(n) + mainLight.color * (0.62h + 0.38h * ndl);
                #if defined(_ADDITIONAL_LIGHTS)
                InputData inputData = (InputData)0;
                inputData.positionWS = input.positionWS;
                inputData.normalWS = n;
                inputData.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(input.positionCS);
                uint lightCount = GetAdditionalLightsCount();
                #if USE_CLUSTER_LIGHT_LOOP
                [loop] for (uint dirIndex = 0u; dirIndex < min(URP_FP_DIRECTIONAL_LIGHTS_COUNT, MAX_VISIBLE_LIGHTS); dirIndex++)
                {
                    Light dl = GetAdditionalLight(dirIndex, input.positionWS, half4(1, 1, 1, 1));
                    lighting += dl.color * dl.distanceAttenuation * 0.6h;
                }
                #endif
                LIGHT_LOOP_BEGIN(lightCount)
                    Light light = GetAdditionalLight(lightIndex, input.positionWS, half4(1, 1, 1, 1));
                    // el rocío dispersa la luz: casi no importa de qué lado llega
                    lighting += light.color * light.distanceAttenuation * (0.55h + 0.45h * saturate(dot(n, light.direction)));
                LIGHT_LOOP_END
                #endif
                #if defined(_ADDITIONAL_LIGHTS_VERTEX)
                lighting += input.vertexLight;
                #endif
                half3 color = albedo * lighting + _Color.rgb * _Glow;
                color = MixFog(color, input.fogFactor);
                return half4(color, 1.0h);
            }
            ENDHLSL
        }
    }

    FallBack Off
}
