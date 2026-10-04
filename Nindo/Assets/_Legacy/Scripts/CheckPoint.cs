using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.SceneManagement;

public class CheckPoint : MonoBehaviour
{
    public Vector3 checkPoint;

    private void OnCollisionEnter(Collision collision)
    {
        if (collision.gameObject.CompareTag("PlayerBody"))
        {
            checkPoint = collision.gameObject.GetComponent<Transform>().position;
            if (checkPoint == null )
            {
                SceneManager.LoadScene(SceneManager.GetActiveScene().name);
            }
            //Debug.Log("Checkpoint guardado");
        }
    }
}
